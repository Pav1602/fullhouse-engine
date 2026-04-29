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
import math
from pathlib import Path
from multiprocessing import Pool

_REPO_ROOT = str(Path(__file__).parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ---------------------------------------------------------------------------
# Top-level worker — must be at module level so it is picklable.
# ---------------------------------------------------------------------------

def _run_one_match(args: tuple) -> dict:
    """
    args: (match_id, bot_paths, seed, n_hands, env_overrides)

    Sets SKANT_* env vars, runs a single match, restores env.
    Returns the run_match result dict (chip_delta, n_hands, bot_errors, ...).
    On any exception, returns a zero-delta result so the pool keeps running.
    """
    # Re-establish repo root in worker (needed for forkserver/spawn start methods)
    _root = str(Path(__file__).parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from sandbox.match import run_match

    match_id, bot_paths, seed, n_hands, env_overrides = args

    # Inject env overrides and remember originals for cleanup
    saved = {}
    for k, v in env_overrides.items():
        saved[k] = os.environ.get(k)
        os.environ[k] = str(v)

    try:
        result = run_match(match_id, bot_paths, n_hands=n_hands, seed=seed)
    except Exception as exc:
        # Return zero-delta on crash so the sweep isn't derailed by a bad trial
        result = {
            "match_id": match_id,
            "chip_delta": {k: 0 for k in bot_paths},
            "bot_errors": {k: [str(exc)] for k in bot_paths},
            "n_hands": 0,
        }
    finally:
        for k, orig in saved.items():
            if orig is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = orig

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compare(
    bot_a_path: str,
    bot_b_path: str,
    opponent_pool: dict,        # {opp_id: opp_path}
    n_seeds: int = 100,
    n_workers: int = 8,
    n_hands: int = 200,
    env_overrides: dict = None, # {"SKANT_RFI_TIGHTNESS": "1.2", ...}
    seed_offset: int = 0,       # first actual seed = seed_offset + 0
) -> dict:
    """
    Compare bot_a vs bot_b against every opponent in opponent_pool using CRN.

    For each (opponent, seed_k), runs 4 matches so both bots see the same
    shuffled deck in the same seat configuration. Averages normal + swapped
    to cancel positional bias, then computes the paired difference per seed.

    When bot_a_path == bot_b_path (fast path): only 2 matches per seed are run.
    b_* fields mirror a_* and paired_diff is 0.0 exactly — halves total compute
    for baseline and sweep self-comparisons.

    seed_offset: actual seeds used are seed_offset, seed_offset+1, …,
    seed_offset+n_seeds-1. Pass seed_offset=batch_size in sweep Phase 2 to
    avoid re-running seeds already evaluated in Phase 1.

    Returns:
        {
            opp_id: {
                "a_mean":             float,   # bot_a mean chip delta (pos-balanced)
                "a_stderr":           float,
                "b_mean":             float,   # bot_b mean chip delta
                "b_stderr":           float,
                "paired_diff_mean":   float,   # mean(a_avg - b_avg) per seed
                "paired_diff_stderr": float,
                "n":                  int,     # = n_seeds paired observations
            },
            ...
        }

    Acceptance test:
        compare(path_A, path_A, pool, n_seeds=5) ->
        paired_diff_mean == 0.0 for every opponent when both bots are
        completely deterministic. For bots with unseeded random decisions
        (like mixed-strategy MC equity), expect |paired_diff_mean| << a_mean
        and paired_diff_stderr < 50 chips (at n_seeds=100).
    """
    import numpy as np

    if env_overrides is None:
        env_overrides = {}

    same_bot = (bot_a_path == bot_b_path)

    # Build flat task list: (match_id, bot_paths, seed, n_hands, env_overrides)
    # task_meta parallel list: (opp_id, config_key, local_i) where local_i is
    #   0-indexed within this compare() call (independent of seed_offset).
    tasks = []
    task_meta = []

    for opp_id, opp_path in opponent_pool.items():
        for i in range(n_seeds):
            actual_seed = seed_offset + i
            # CRITICAL: "a" and "b" runs share the SAME match_id so that bots
            # which seed their RNG from hand_id (e.g. skantbot3's get_hand_rng)
            # produce identical decisions in both runs → paired_diff cancels exactly.
            mid_norm = f"cmp_{opp_id}_{actual_seed}_norm"
            mid_swap = f"cmp_{opp_id}_{actual_seed}_swap"

            # bot_a normal: bot_a in seat 0
            tasks.append((mid_norm, {"bot_a": bot_a_path, opp_id: opp_path},
                          actual_seed, n_hands, env_overrides))
            task_meta.append((opp_id, "a_normal", i))
            # bot_a swapped: bot_a in seat 1
            tasks.append((mid_swap, {opp_id: opp_path, "bot_a": bot_a_path},
                          actual_seed, n_hands, env_overrides))
            task_meta.append((opp_id, "a_swapped", i))

            if not same_bot:
                # bot_b normal: bot_b in seat 0 — SAME match_id as a_normal
                tasks.append((mid_norm, {"bot_b": bot_b_path, opp_id: opp_path},
                              actual_seed, n_hands, env_overrides))
                task_meta.append((opp_id, "b_normal", i))
                # bot_b swapped: bot_b in seat 1 — SAME match_id as a_swapped
                tasks.append((mid_swap, {opp_id: opp_path, "bot_b": bot_b_path},
                              actual_seed, n_hands, env_overrides))
                task_meta.append((opp_id, "b_swapped", i))

    # Run all tasks in parallel
    with Pool(processes=n_workers) as pool:
        results = pool.map(_run_one_match, tasks)

    # Aggregate per-seed deltas: opp_id -> local_i -> config_key -> chip_delta
    raw: dict = {}
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
            # Fast path: b identical to a, paired diff trivially zero
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
