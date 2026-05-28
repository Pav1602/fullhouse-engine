"""
Fullhouse Harness — CRN-based match comparison.

compare(bot_a_path, bot_b_path, opponent_pool, n_seeds, n_workers) -> dict

For each opponent in the pool, runs 4 matches per seed:
  - bot_a normal   (bot_a seat 0, opp seat 1)
  - bot_a swapped  (opp seat 0, bot_a seat 1)
  - bot_b normal   (bot_b seat 0, opp seat 1)
  - bot_b swapped  (opp seat 0, bot_b seat 1)

All four share the same seed_k so both bots see the same shuffled deck
(Common Random Numbers). Averaging normal+swapped cancels positional bias.

Fast path: when bot_a_path == bot_b_path (baseline / sweep self-comparison),
  only 2 matches per seed are run (normal + swapped). b_* stats are copied from
  a_* and paired_diff is set to 0.0 exactly, halving total compute.

seed_offset: seeds used are range(seed_offset, seed_offset + n_seeds). Used by
  sweep.py to avoid overlap between the quick-eval batch and the full-eval phase.

Acceptance test: compare(path_A, path_A, pool, n_seeds=5) must produce
  paired_diff_mean == 0.0 exactly for every opponent.
"""

import os
import sys
import random
import math
import json
import asyncio
import time
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from engine.game import PokerEngine, STARTING_STACK

# ---------------------------------------------------------------------------
# Async Worker
# ---------------------------------------------------------------------------

class AsyncBotProcess:
    def __init__(self, bot_id: str, bot_path: str, env_overrides: dict):
        self.bot_id = bot_id
        self.bot_path = bot_path
        self.env_overrides = env_overrides or {}
        self.errors = []
        self._proc = None

    async def start(self):
        env = {**os.environ, "BOT_PATH": self.bot_path, "ACTION_TIMEOUT": "2"}
        for k, v in self.env_overrides.items():
            env[k] = str(v)

        runner_path = Path(__file__).parent.parent / "sandbox" / "runner.py"
        cmd = [sys.executable, "-u", str(runner_path)]

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        return self

    async def act(self, game_state: dict) -> dict:
        try:
            msg = json.dumps(game_state) + "\n"
            self._proc.stdin.write(msg.encode("utf-8"))
            await self._proc.stdin.drain()

            line = await self._proc.stdout.readline()
            if not line:
                raise EOFError("Bot process died")
            
            action = json.loads(line.decode("utf-8").strip())
            if "error" in action:
                self.errors.append(action["error"])
            return action
        except Exception as e:
            self.errors.append(str(e))
            return {"action": "fold", "error": str(e)}

    async def stop(self):
        if not self._proc:
            return
        try:
            self._proc.stdin.close()
        except Exception:
            pass
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            try:
                self._proc.kill()
                await self._proc.wait()
            except ProcessLookupError:
                pass


async def async_run_match(match_id: str, bot_paths: dict, n_hands: int, seed: int, env_overrides: dict) -> dict:
    bot_ids = list(bot_paths.keys())
    
    env_overrides = dict(env_overrides) if env_overrides else {}
    env_overrides["SKANT_MATCH_ID"] = match_id

    procs = {}
    for bid, path in bot_paths.items():
        proc = AsyncBotProcess(bid, path, env_overrides)
        await proc.start()
        procs[bid] = proc

    stacks = {bid: STARTING_STACK for bid in bot_ids}
    hand_log = []
    dealer = 0
    start_ts = time.time()

    try:
        for hand_num in range(n_hands):
            alive = [bid for bid in bot_ids if stacks[bid] > 0]
            if len(alive) < 2:
                break

            hand_id = f"{match_id}_h{hand_num:04d}"
            hand_seed = (seed * 1000003 + hand_num) if seed is not None else None
            
            engine = PokerEngine(
                hand_id=hand_id,
                bot_ids=alive,
                dealer_seat=dealer % len(alive),
                starting_stacks={bid: stacks[bid] for bid in alive},
                seed=hand_seed,
            )

            state = engine.start_hand()
            steps = 0

            while state.get("type") == "action_request":
                seat = state["seat_to_act"]
                bot_id = alive[seat]
                action = await procs[bot_id].act(state)

                state = engine.apply_action(seat, action)
                steps += 1
                if steps > 1000:
                    raise RuntimeError(f"Hand exceeded 1000 steps: {engine.hand_id}")

            if state.get("type") == "hand_complete":
                state["all_hole_cards"] = {p.bot_id: [str(c) for c in p.hole_cards] for p in engine.players}
                for bot_id in alive:
                    try:
                        await procs[bot_id].act(state)
                    except Exception:
                        pass

            hand_log.append({"hand_num": hand_num, "hand_id": hand_id, **state})

            for bid, s in state["final_stacks"].items():
                stacks[bid] = s

            dealer += 1
    finally:
        for p in procs.values():
            await p.stop()

    return {
        "match_id": match_id,
        "bot_ids": bot_ids,
        "n_hands": len(hand_log),
        "duration_s": round(time.time() - start_ts, 2),
        "final_stacks": stacks,
        "chip_delta": {bid: stacks[bid] - STARTING_STACK for bid in bot_ids},
        "bot_errors": {bid: procs[bid].errors for bid in bot_ids},
        "hands": hand_log,
    }

async def _run_one_match_task(sem, args):
    match_id, bot_paths, seed, n_hands, env_overrides = args
    async with sem:
        try:
            return await async_run_match(match_id, bot_paths, n_hands, seed, env_overrides)
        except Exception as exc:
            return {
                "match_id": match_id,
                "chip_delta": {k: 0 for k in bot_paths},
                "bot_errors": {k: [str(exc)] for k in bot_paths},
                "n_hands": 0,
            }

async def _run_all_tasks(tasks, max_concurrent_matches, show_progress):
    sem = asyncio.Semaphore(max_concurrent_matches)
    if show_progress:
        import tqdm
        pbar = tqdm.tqdm(total=len(tasks), desc="Matches")
        async def tracking_worker(t):
            res = await _run_one_match_task(sem, t)
            pbar.update(1)
            return res
        coros = [tracking_worker(t) for t in tasks]
        results = await asyncio.gather(*coros)
        pbar.close()
        return results
    else:
        coros = [_run_one_match_task(sem, t) for t in tasks]
        return await asyncio.gather(*coros)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def aggregate_by_opponent(per_table_results: dict) -> dict:
    opp_totals = {}
    for table_id, data in per_table_results.items():
        for opp in data["opponents"]:
            if opp not in opp_totals:
                opp_totals[opp] = {
                    "a_means": [],
                    "b_means": [],
                    "paired_diffs": [],
                    "n_total": 0
                }
            opp_totals[opp]["a_means"].append(data["a_mean"])
            opp_totals[opp]["b_means"].append(data["b_mean"])
            opp_totals[opp]["paired_diffs"].append(data["paired_diff_mean"])
            opp_totals[opp]["n_total"] += data["n"]
            
    import numpy as np
    def _stderr(arr):
        n = len(arr)
        return float(np.std(arr, ddof=1) / math.sqrt(n)) if n > 1 else 0.0

    aggregated = {}
    for opp, totals in opp_totals.items():
        n = len(totals["a_means"])
        aggregated[opp] = {
            "a_mean": float(np.mean(totals["a_means"])) if n > 0 else 0.0,
            "a_stderr": _stderr(totals["a_means"]),
            "b_mean": float(np.mean(totals["b_means"])) if n > 0 else 0.0,
            "b_stderr": _stderr(totals["b_means"]),
            "paired_diff_mean": float(np.mean(totals["paired_diffs"])) if n > 0 else 0.0,
            "paired_diff_stderr": _stderr(totals["paired_diffs"]),
            "n": totals["n_total"],
        }
    return aggregated

def compare(
    bot_a_path: str,
    bot_b_path: str,
    opponent_pool: dict,
    n_seeds: int = 100,
    n_workers: int = 8,
    n_hands: int = 200,
    env_overrides: dict = None,
    seed_offset: int = 0,
    show_progress: bool = False,
    mode: str = "6max",
    n_tables: int = 10,
    max_concurrent_matches: int = None,
) -> dict:
    if max_concurrent_matches is None:
        max_concurrent_matches = min(n_workers * 4, 192)

    if mode.lower() == "hu":
        return _compare_hu(
            bot_a_path=bot_a_path,
            bot_b_path=bot_b_path,
            opponent_pool=opponent_pool,
            n_seeds=n_seeds,
            n_hands=n_hands,
            env_overrides=env_overrides,
            seed_offset=seed_offset,
            show_progress=show_progress,
            max_concurrent_matches=max_concurrent_matches
        )
    elif mode.lower() == "6max":
        return _compare_6max(
            bot_a_path=bot_a_path,
            bot_b_path=bot_b_path,
            opponent_pool=opponent_pool,
            n_seeds=n_seeds,
            n_hands=n_hands,
            env_overrides=env_overrides,
            seed_offset=seed_offset,
            show_progress=show_progress,
            n_tables=n_tables,
            max_concurrent_matches=max_concurrent_matches
        )
    else:
        raise ValueError(f"Unknown mode {mode}")

def _compare_6max(
    bot_a_path: str,
    bot_b_path: str,
    opponent_pool: dict,
    n_seeds: int,
    n_hands: int,
    env_overrides: dict,
    seed_offset: int,
    show_progress: bool,
    n_tables: int,
    max_concurrent_matches: int,
) -> dict:
    import numpy as np

    if env_overrides is None:
        env_overrides = {}

    same_bot = (bot_a_path == bot_b_path)
    
    tasks = []
    task_meta = []
    pool_keys = list(opponent_pool.keys())
    table_configs = {}
    
    for i in range(n_seeds):
        actual_seed = seed_offset + i
        for t_idx in range(n_tables):
            rng = random.Random(f"{actual_seed}_{t_idx}")
            sampled_opp_ids = rng.sample(pool_keys, 5)
            table_id = "table_" + "_".join(sorted(sampled_opp_ids))
            
            table_configs[table_id] = sampled_opp_ids
            
            S_rng = random.Random(f"seat_{actual_seed}_{t_idx}")
            S = S_rng.randint(0, 5)
            arr1_seat = S
            arr2_seat = (S + 3) % 6
            
            mid_norm = f"cmp_{table_id}_{actual_seed}_norm"
            mid_swap = f"cmp_{table_id}_{actual_seed}_swap"
            
            def make_bot_dict(seat_for_test_bot, test_bot_path):
                bdict = {}
                opp_idx = 0
                for pos in range(6):
                    if pos == seat_for_test_bot:
                        bdict[f"test_bot_{pos}"] = test_bot_path
                    else:
                        opp_id = sampled_opp_ids[opp_idx]
                        bdict[f"{opp_id}_{pos}"] = opponent_pool[opp_id]
                        opp_idx += 1
                return bdict
                
            bot_a_norm_dict = make_bot_dict(arr1_seat, bot_a_path)
            bot_a_swap_dict = make_bot_dict(arr2_seat, bot_a_path)
            
            tasks.append((mid_norm, bot_a_norm_dict, actual_seed, n_hands, env_overrides))
            task_meta.append((table_id, "a_normal", i, arr1_seat))
            
            tasks.append((mid_swap, bot_a_swap_dict, actual_seed, n_hands, env_overrides))
            task_meta.append((table_id, "a_swapped", i, arr2_seat))

            if not same_bot:
                bot_b_norm_dict = make_bot_dict(arr1_seat, bot_b_path)
                bot_b_swap_dict = make_bot_dict(arr2_seat, bot_b_path)
                
                tasks.append((mid_norm, bot_b_norm_dict, actual_seed, n_hands, env_overrides))
                task_meta.append((table_id, "b_normal", i, arr1_seat))
                
                tasks.append((mid_swap, bot_b_swap_dict, actual_seed, n_hands, env_overrides))
                task_meta.append((table_id, "b_swapped", i, arr2_seat))

    results = asyncio.run(_run_all_tasks(tasks, max_concurrent_matches, show_progress))

    raw = {}
    for (table_id, config_key, local_i, test_seat), result in zip(task_meta, results):
        cd = result.get("chip_delta", {})
        test_bot_key = f"test_bot_{test_seat}"
        val = cd.get(test_bot_key, 0)
        raw.setdefault(table_id, {}).setdefault(local_i, {})[config_key] = val

    def _stderr(arr):
        n = len(arr)
        return float(np.std(arr, ddof=1) / math.sqrt(n)) if n > 1 else 0.0

    output = {}
    for table_id, opps in table_configs.items():
        seed_data = raw.get(table_id, {})
        a_deltas = []
        b_deltas = []
        paired_diffs = []
        for i in range(n_seeds):
            sd = seed_data.get(i, {})
            a_norm = sd.get("a_normal", 0)
            a_swap = sd.get("a_swapped", 0)
            a_avg = (a_norm + a_swap) / 2.0
            a_deltas.append(a_avg)
            
            if not same_bot:
                b_norm = sd.get("b_normal", 0)
                b_swap = sd.get("b_swapped", 0)
                b_avg = (b_norm + b_swap) / 2.0
                b_deltas.append(b_avg)
                paired_diffs.append(a_avg - b_avg)

        a_arr = np.array(a_deltas)
        if same_bot:
            output[table_id] = {
                "opponents": opps,
                "a_mean": float(np.mean(a_arr)),
                "a_stderr": _stderr(a_arr),
                "b_mean": float(np.mean(a_arr)),
                "b_stderr": _stderr(a_arr),
                "paired_diff_mean": 0.0,
                "paired_diff_stderr": 0.0,
                "n": n_seeds,
            }
        else:
            b_arr = np.array(b_deltas)
            d_arr = np.array(paired_diffs)
            output[table_id] = {
                "opponents": opps,
                "a_mean": float(np.mean(a_arr)),
                "a_stderr": _stderr(a_arr),
                "b_mean": float(np.mean(b_arr)),
                "b_stderr": _stderr(b_arr),
                "paired_diff_mean": float(np.mean(d_arr)),
                "paired_diff_stderr": _stderr(d_arr),
                "n": n_seeds,
            }
    return output

def _compare_hu(
    bot_a_path: str,
    bot_b_path: str,
    opponent_pool: dict,
    n_seeds: int,
    n_hands: int,
    env_overrides: dict,
    seed_offset: int,
    show_progress: bool,
    max_concurrent_matches: int,
) -> dict:
    import numpy as np

    if env_overrides is None:
        env_overrides = {}

    same_bot = (bot_a_path == bot_b_path)
    tasks = []
    task_meta = []

    for opp_id, opp_path in opponent_pool.items():
        for i in range(n_seeds):
            actual_seed = seed_offset + i
            mid_norm = f"cmp_{opp_id}_{actual_seed}_norm"
            mid_swap = f"cmp_{opp_id}_{actual_seed}_swap"

            tasks.append((mid_norm, {"bot_a": bot_a_path, opp_id: opp_path}, actual_seed, n_hands, env_overrides))
            task_meta.append((opp_id, "a_normal", i))
            
            tasks.append((mid_swap, {opp_id: opp_path, "bot_a": bot_a_path}, actual_seed, n_hands, env_overrides))
            task_meta.append((opp_id, "a_swapped", i))

            if not same_bot:
                tasks.append((mid_norm, {"bot_b": bot_b_path, opp_id: opp_path}, actual_seed, n_hands, env_overrides))
                task_meta.append((opp_id, "b_normal", i))
                
                tasks.append((mid_swap, {opp_id: opp_path, "bot_b": bot_b_path}, actual_seed, n_hands, env_overrides))
                task_meta.append((opp_id, "b_swapped", i))

    results = asyncio.run(_run_all_tasks(tasks, max_concurrent_matches, show_progress))

    raw = {}
    for (opp_id, config_key, local_i), result in zip(task_meta, results):
        cd = result.get("chip_delta", {})
        raw.setdefault(opp_id, {}).setdefault(local_i, {})[config_key] = cd

    def _stderr(arr):
        n = len(arr)
        return float(np.std(arr, ddof=1) / math.sqrt(n)) if n > 1 else 0.0

    output = {}
    for opp_id in opponent_pool:
        seed_data = raw.get(opp_id, {})
        a_deltas = []
        b_deltas = []
        paired_diffs = []

        for i in range(n_seeds):
            sd = seed_data.get(i, {})
            a_norm = sd.get("a_normal",  {}).get("bot_a", 0)
            a_swap = sd.get("a_swapped", {}).get("bot_a", 0)
            a_avg  = (a_norm + a_swap) / 2.0
            a_deltas.append(a_avg)
            if not same_bot:
                b_norm = sd.get("b_normal",  {}).get("bot_b", 0)
                b_swap = sd.get("b_swapped", {}).get("bot_b", 0)
                b_avg  = (b_norm + b_swap) / 2.0
                b_deltas.append(b_avg)
                paired_diffs.append(a_avg - b_avg)

        a_arr = np.array(a_deltas)

        if same_bot:
            output[opp_id] = {
                "a_mean":             float(np.mean(a_arr)),
                "a_stderr":           _stderr(a_arr),
                "b_mean":             float(np.mean(a_arr)),
                "b_stderr":           _stderr(a_arr),
                "paired_diff_mean":   0.0,
                "paired_diff_stderr": 0.0,
                "n":                  n_seeds,
            }
        else:
            b_arr = np.array(b_deltas)
            d_arr = np.array(paired_diffs)

            output[opp_id] = {
                "a_mean":             float(np.mean(a_arr)),
                "a_stderr":           _stderr(a_arr),
                "b_mean":             float(np.mean(b_arr)),
                "b_stderr":           _stderr(b_arr),
                "paired_diff_mean":   float(np.mean(d_arr)),
                "paired_diff_stderr": _stderr(d_arr),
                "n":                  n_seeds,
            }

    return output
