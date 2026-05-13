"""
Optuna TPE multi-objective sweep to tune skantbot4 Config parameters.

Only run this AFTER:
  1. Phases 1-3 are verified (baseline runs cleanly)
  2. LLM-generated bots have been added to harness/opponents/llm_generated/
     and their paths registered in registry.py

Objectives (both MAXIMISED):
  1. mean_perf  = mean(chip_delta per opponent)    — overall average
  2. worst_perf = min(chip_delta per opponent)     — worst-case robustness

Usage:
    # Quick sanity check (3 trials, 5 seeds)
    python3 harness/sweep.py --trials 3 --seeds 5 --workers 2 --hands 50

    # Production run (start small to validate direction)
    python3 harness/sweep.py --trials 200 --seeds 20 --workers 8

    # Full sweep
    python3 harness/sweep.py --trials 2000 --seeds 50 --workers 8

    # Resume an interrupted sweep
    python3 harness/sweep.py --trials 2000 --seeds 50 --resume --study-name skantbot4_sweep
"""

import sys
import json
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_RESULTS_DIR = Path(__file__).parent / "results"

# ---------------------------------------------------------------------------
# Parameter search space
# (MC sim counts, sizing presets excluded from v1)
# ---------------------------------------------------------------------------
PARAM_SPACE = {
    # --- Small open defense ---
    "small_open_threshold_bb": ("float", 2.05, 2.25),
    "small_open_3bet_boost": ("float", 1.0, 2.0),
    "small_open_call_boost": ("float", 1.0, 2.5),

    # --- Preflop tightness & multipliers ---
    "rfi_tightness": ("float", 0.8, 2.2),
    "threebet_tightness": ("float", 0.8, 2.2),
    "fourbet_tightness": ("float", 0.8, 1.5),
    "stack_short_tightness": ("float", 0.7, 1.1),
    "shrink_widening_factor": ("float", 0.0, 0.05),
    "cold_start_caution": ("float", 0.0, 0.02),

    # --- Positional aggression multipliers ---
    "pos_aggression_lj": ("float", 0.8, 1.2),
    "pos_aggression_hj": ("float", 0.8, 1.2),
    "pos_aggression_co": ("float", 0.8, 1.2),
    "pos_aggression_btn": ("float", 0.8, 1.2),
    "pos_aggression_sb": ("float", 0.8, 1.2),
    "pos_aggression_bb": ("float", 0.8, 1.2),

    # --- Preflop sizing multipliers ---
    "open_size_bb": ("float", 2.0, 2.5),
    "threebet_size_ip": ("float", 2.8, 4.5),
    "threebet_size_oop": ("float", 3.0, 4.5),

    # --- Postflop equity thresholds ---
    "equity_value_bet": ("float", 0.55, 0.75),
    "equity_thin_value": ("float", 0.48, 0.60),
    "equity_call_threshold": ("float", 0.30, 0.45),
    "equity_raise_threshold": ("float", 0.75, 0.90),
    "pot_odds_buffer_normal": ("float", 0.05, 0.20),
    "pot_odds_buffer_marginal": ("float", 0.10, 0.30),

    # --- Stack preservation & Jam guards ---
    "stack_risk_high_eq_normal": ("float", 0.75, 0.95),
    "stack_risk_high_eq_maniac": ("float", 0.65, 0.85),
    "stack_risk_med_eq_normal": ("float", 0.50, 0.70),
    "stack_risk_med_eq_maniac": ("float", 0.55, 0.75),
    "fourbet_commit_threshold": ("float", 0.15, 0.35),
    "fourbet_call_threshold_pct": ("float", 0.05, 0.25),
    "threebet_call_threshold_pct": ("float", 0.05, 0.25),

    # --- Bet sizing presets ---
    "sizing_value": ("float", 0.60, 1.00),
    "cbet_size_pct": ("float", 0.25, 0.60),

    # --- C-bet & Texture coefficients ---
    "cbet_freq_base": ("float", 0.65, 0.95),
    "k_texture_paired": ("float", -0.2, 0.2),
    "k_texture_monotone": ("float", -0.2, 0.2),
    "k_texture_connected": ("float", -0.2, 0.2),
    "k_texture_high_card": ("float", -0.2, 0.2),
    "cbet_multiway_penalty": ("float", 0.5, 1.0),
    "spr_commit_threshold": ("float", 2.0, 6.0),
    "spr_smoothness": ("float", 1.0, 3.0),

    # --- River Aggression & Sizing modifiers ---
    "river_mdf_aggression": ("float", 0.5, 1.5),
    "river_v2b_half_pot": ("float", 1.0, 3.0),
    "river_v2b_pot_sized": ("float", 0.5, 2.0),
    "river_v2b_overbet": ("float", 0.1, 1.0),
    "k_river_bluff_blocker": ("float", -0.2, 0.2),
    "river_value_thin_threshold": ("float", 0.55, 0.70),
    "river_value_strong_threshold": ("float", 0.75, 0.90),
    "river_value_thin_size": ("float", 0.30, 0.65),
    "river_value_strong_size": ("float", 0.70, 1.20),

    # --- Bluffing ---
    "bluff_freq_ip": ("float", 0.05, 0.35),
    "bluff_freq_oop": ("float", 0.0, 0.15),

    # --- Match standing & Commitment ---
    "k_commit": ("float", 0.0, 0.2),
    "k_standing": ("float", 0.0, 0.5),
    "standing_alpha": ("float", 0.0, 0.5),
    "standing_beta": ("float", 0.0, 0.5),

    # --- Counter-exploit modeling & profiles ---
    "maniac_vpip_threshold": ("float", 0.45, 0.60),
    "station_vpip_threshold": ("float", 0.30, 0.45),
    "k_bluff_vs_cbet_folder": ("float", 0.0, 0.5),
    "k_bluff_vs_2barrel_folder": ("float", 0.0, 0.5),
    "k_bluff_vs_3barrel_folder": ("float", 0.0, 0.5),
    "k_bluff_vs_wtsd": ("float", 0.0, 0.5),
    "k_value_size_vs_station": ("float", 0.0, 0.5),
    "k_tightness_vs_3bet_freq": ("float", 0.0, 0.5),
    "k_call_threshold_vs_aggression": ("float", 0.0, 0.5),
    "k_4bet_vs_3bet_freq": ("float", 0.0, 0.5),
    "variance_c": ("float", 0.0, 0.5),
}

# ---------------------------------------------------------------------------
# Single-trial evaluation (runs compare() with this trial's params)
# ---------------------------------------------------------------------------

def _evaluate_params(
    trial_params: dict,
    opponent_pool: dict,
    skant_path: str,
    n_seeds: int,
    n_hands: int,
    n_workers: int,
) -> dict:
    """Run skantbot4 with trial_params against pool. Returns compare() dict."""
    from harness.match_runner import compare

    env_overrides = {
        f"SKANT_{k.upper()}": str(v)
        for k, v in trial_params.items()
    }
    # compare(A, A) with env_overrides → a_mean = absolute perf of tuned bot
    return compare(
        bot_a_path=skant_path,
        bot_b_path=skant_path,
        opponent_pool=opponent_pool,
        n_seeds=n_seeds,
        n_workers=n_workers,
        n_hands=n_hands,
        env_overrides=env_overrides,
    )


# ---------------------------------------------------------------------------
# Optuna objective (multi-objective: mean + worst-case)
# ---------------------------------------------------------------------------

def make_objective(
    opponent_pool: dict,
    skant_path: str,
    n_seeds: int,
    n_hands: int,
    n_workers: int,
    batch_size: int = 10,
):
    """
    Returns an Optuna objective for TPE multi-objective optimisation.

    NOTE: Optuna does not support trial.report() for multi-objective studies,
    so we implement manual early termination: after the first batch (batch_size
    seeds), if the running mean is clearly below 0 AND a positive-mean trial
    has been seen before, we prune the trial manually by returning very negative
    sentinel values. This catches clearly bad configs without native pruner support.

    Returns: (mean_perf, worst_perf) — both to be maximised.
    """
    import optuna
    from harness.match_runner import compare

    # Track the best mean seen so far across completed trials
    _state = {"best_mean_seen": None}

    def objective(trial: "optuna.Trial"):
        params = {}
        for name, (dtype, lo, hi) in PARAM_SPACE.items():
            if dtype == "float":
                params[name] = trial.suggest_float(name, lo, hi)
            elif dtype == "int":
                params[name] = trial.suggest_int(name, int(lo), int(hi))

        env_overrides = {f"SKANT_{k.upper()}": str(v) for k, v in params.items()}

        # --- Phase 1: quick eval (batch_size seeds) ---
        quick_results = compare(
            bot_a_path=skant_path,
            bot_b_path=skant_path,
            opponent_pool=opponent_pool,
            n_seeds=batch_size,
            n_workers=n_workers,
            n_hands=n_hands,
            env_overrides=env_overrides,
        )
        quick_means  = [s["a_mean"] for s in quick_results.values()]
        quick_mean   = sum(quick_means) / len(quick_means)
        quick_worst  = min(quick_means)

        # Manual early termination: prune if quick mean is clearly bad
        best = _state["best_mean_seen"]
        if best is not None and quick_mean < best - 2000:
            # Far below best seen — skip full evaluation
            raise optuna.TrialPruned()

        # --- Phase 2: full eval (remaining seeds, non-overlapping) ---
        remaining = n_seeds - batch_size
        if remaining > 0:
            full_results = compare(
                bot_a_path=skant_path,
                bot_b_path=skant_path,
                opponent_pool=opponent_pool,
                n_seeds=remaining,
                n_workers=n_workers,
                n_hands=n_hands,
                env_overrides=env_overrides,
                seed_offset=batch_size,   # start after Phase 1 seeds
            )
            # Weighted average (batch_size + remaining)
            per_opp_means = {}
            for opp_id in opponent_pool:
                q = quick_results[opp_id]["a_mean"]
                f = full_results[opp_id]["a_mean"]
                per_opp_means[opp_id] = (q * batch_size + f * remaining) / n_seeds
        else:
            per_opp_means = {opp_id: quick_results[opp_id]["a_mean"]
                             for opp_id in opponent_pool}

        mean_perf  = sum(per_opp_means.values()) / len(per_opp_means)
        worst_perf = min(per_opp_means.values())

        # Update best mean tracker
        if _state["best_mean_seen"] is None or mean_perf > _state["best_mean_seen"]:
            _state["best_mean_seen"] = mean_perf

        # Store per-opponent breakdown as trial user attributes for analysis
        for opp_id, m in per_opp_means.items():
            trial.set_user_attr(f"{opp_id}_mean", m)

        return mean_perf, worst_perf

    return objective


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_sweep(
    n_trials:    int  = 2000,
    n_seeds:     int  = 50,
    n_hands:     int  = 200,
    n_workers:   int  = 8,
    batch_size:  int  = 10,
    study_name:  str  = "skantbot4_sweep",
    storage:     str  = None,
    resume:      bool = False,
) -> "optuna.Study":
    import optuna
    from harness.opponents.registry import (
        load_pool, validate_pool, SKANTBOT_TUNABLE_PATH
    )

    pool = load_pool(include_heldout=False)
    validate_pool(pool)

    _RESULTS_DIR.mkdir(exist_ok=True)
    if storage is None:
        storage = f"sqlite:///{_RESULTS_DIR}/sweep_{study_name}.db"

    sampler = optuna.samplers.TPESampler(seed=42)
    # NOTE: SuccessiveHalvingPruner is not supported for multi-objective studies
    # (trial.report() raises NotImplementedError). Manual early termination is
    # implemented inside make_objective() instead.
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        sampler=sampler,
        directions=["maximize", "maximize"],   # mean_perf, worst_perf
        load_if_exists=resume,
    )

    objective = make_objective(
        opponent_pool=pool,
        skant_path=SKANTBOT_TUNABLE_PATH,
        n_seeds=n_seeds,
        n_hands=n_hands,
        n_workers=n_workers,
        batch_size=batch_size,
    )

    print(f"=== Optuna Sweep: {study_name} ===")
    print(f"Tuning {len(PARAM_SPACE)} parameters over {len(pool)} opponents")
    print(f"Trials: {n_trials}  |  Seeds/trial: {n_seeds}  |  Workers: {n_workers}")
    print(f"Storage: {storage}\n")

    study.optimize(
        objective,
        n_trials=n_trials,
        show_progress_bar=True,
    )

    # Print Pareto front
    pareto = study.best_trials
    print(f"\n=== Pareto Front ({len(pareto)} solutions) ===")
    print(f"{'Trial':>6} {'Mean Perf':>12} {'Worst Perf':>12}")
    print("-" * 34)
    for t in sorted(pareto, key=lambda t: -t.values[0]):
        print(f"{t.number:>6} {t.values[0]:>+12.1f} {t.values[1]:>+12.1f}")

    # Save best config (hard floor on worst performance)
    worst_floor = -3000
    survivors = [t for t in pareto if t.values[1] >= worst_floor]
    if not survivors:
        best_worst = max(t.values[1] for t in pareto) if pareto else float('-inf')
        raise ValueError(
            f"No trial achieved worst_perf >= {worst_floor}. "
            f"Best worst_perf was {best_worst:.1f}. "
            f"Either lower the floor, fix the strategy structure, or extend the sweep."
        )
    best = max(survivors, key=lambda t: t.values[0])
    best_path = _RESULTS_DIR / f"best_params_{study_name}.json"
    best_path.write_text(json.dumps({
        "trial_number": best.number,
        "mean_perf":    best.values[0],
        "worst_perf":   best.values[1],
        "params":       best.params,
        "env_vars":     {f"SKANT_{k.upper()}": str(v)
                         for k, v in best.params.items()},
    }, indent=2))
    print(f"\nBest params saved: {best_path}")

    return study


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Optuna sweep for skantbot4")
    p.add_argument("--trials",      type=int, default=2000)
    p.add_argument("--seeds",       type=int, default=50)
    p.add_argument("--hands",       type=int, default=200)
    p.add_argument("--workers",     type=int, default=8)
    p.add_argument("--batch-size",  type=int, default=10,
                   help="Seeds per pruning batch (default: 10)")
    p.add_argument("--study-name",  default="skantbot4_sweep")
    p.add_argument("--storage",     default=None,
                   help="SQLite URL (default: harness/results/sweep_<name>.db)")
    p.add_argument("--resume",      action="store_true",
                   help="Resume an existing study from storage")
    args = p.parse_args()
    run_sweep(
        n_trials=args.trials,
        n_seeds=args.seeds,
        n_hands=args.hands,
        n_workers=args.workers,
        batch_size=args.batch_size,
        study_name=args.study_name,
        storage=args.storage,
        resume=args.resume,
    )
