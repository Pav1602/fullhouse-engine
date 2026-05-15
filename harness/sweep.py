"""
Optuna TPE multi-objective sweep to tune skantbot4 Config parameters.

Only run this AFTER:
  1. Phases 1-3 are verified (baseline runs cleanly)
  2. LLM-generated bots have been added to harness/opponents/llm_generated/
     and their paths registered in registry.py

Objectives (both MAXIMISED):
  1. mean_perf  = mean(chip_delta per opponent)    — overall average
  2. worst_perf = min(chip_delta per opponent)     — worst-case robustness
  3. unseen_mean = mean(chip_delta on validation pool) — generalisation

Usage:
    # Full sweep as requested
    python -m harness.sweep \
        --trials 1500 \
        --seeds 40 \
        --workers 16 \
        --study-name skantbot6_generalisation_sweep \
        --storage sqlite:///harness/results/sweep_skantbot6_gen.db
"""

import sys
import json
import importlib
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_RESULTS_DIR = Path(__file__).parent / "results"

# ---------------------------------------------------------------------------
# Parameter search space
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

    # --- Stack preservation guards ---
    "stack_risk_high_eq_normal": ("float", 0.75, 0.95),
    "stack_risk_high_eq_maniac": ("float", 0.65, 0.85),
    "stack_risk_med_eq_normal": ("float", 0.50, 0.70),
    "stack_risk_med_eq_maniac": ("float", 0.55, 0.75),

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

    # --- River Aggression & thresholds ---
    "river_mdf_aggression": ("float", 0.5, 1.5),
    "k_river_bluff_blocker": ("float", -0.2, 0.2),
    "river_value_thin_threshold": ("float", 0.55, 0.70),
    "river_value_strong_threshold": ("float", 0.75, 0.90),

    # --- Bluffing ---
    "bluff_freq_ip": ("float", 0.05, 0.35),
    "bluff_freq_oop": ("float", 0.0, 0.15),

    # --- Match standing & Commitment ---
    "k_commit": ("float", 0.0, 0.2),
    "k_standing": ("float", 0.0, 0.5),
    "standing_alpha": ("float", 0.0, 0.5),
    "standing_beta": ("float", 0.0, 0.5),

    # --- Counter-exploit modeling ---
    "k_bluff_vs_cbet_folder": ("float", 0.0, 0.5),
    "k_bluff_vs_2barrel_folder": ("float", 0.0, 0.5),
    "k_bluff_vs_3barrel_folder": ("float", 0.0, 0.5),
    "k_bluff_vs_wtsd": ("float", 0.0, 0.5),
    "k_value_size_vs_station": ("float", 0.0, 0.5),
    "k_tightness_vs_3bet_freq": ("float", 0.0, 0.5),
    "k_call_threshold_vs_aggression": ("float", 0.0, 0.5),
    "k_4bet_vs_3bet_freq": ("float", 0.0, 0.5),
    "variance_c": ("float", 0.0, 0.2), # reduced from 0.5 per Claude's suggestion
    
    # --- Smooth-detection Softness & Thresholds (Phase 2) ---
    "maniac_softness": ("float", 1e-4, 0.10),
    "station_softness": ("float", 1e-4, 0.10),
    "maniac_vpip_threshold": ("float", 0.40, 0.60),
    "maniac_pfr_threshold": ("float", 0.30, 0.50),
    "station_vpip_threshold": ("float", 0.25, 0.45),
    "station_pfr_threshold": ("float", 0.05, 0.25),

    # --- Thin Value OOP ---
    "oop_passive_value_threshold": ("float", 0.45, 0.60),
    "oop_passive_value_size": ("float", 0.25, 0.60),
    "passive_aggression_threshold": ("float", 0.15, 0.45),
}

# ---------------------------------------------------------------------------
# Optuna objective
# ---------------------------------------------------------------------------

def make_objective(
    train_pool: dict,
    validation_pool: dict,
    skant_path: str,
    n_seeds: int,
    n_hands: int,
    n_workers: int,
    batch_size: int = 10,
):
    import optuna
    from harness.match_runner import compare

    _state = {"best_mean_seen": None}

    def objective(trial: "optuna.Trial"):
        params = {}
        for name, (dtype, lo, hi) in PARAM_SPACE.items():
            if dtype == "float":
                params[name] = trial.suggest_float(name, lo, hi)
            elif dtype == "int":
                params[name] = trial.suggest_int(name, int(lo), int(hi))

        env_overrides = {f"SKANT_{k.upper()}": str(v) for k, v in params.items()}

        # Phase 1: quick eval on train pool (batch_size seeds)
        quick_results = compare(
            bot_a_path=skant_path,
            bot_b_path=skant_path,
            opponent_pool=train_pool,
            n_seeds=batch_size,
            n_workers=n_workers,
            n_hands=n_hands,
            env_overrides=env_overrides,
        )
        quick_means  = [s["a_mean"] for s in quick_results.values()]
        quick_mean   = sum(quick_means) / len(quick_means)
        quick_worst  = min(quick_means)

        if quick_worst < -2000:
            raise optuna.TrialPruned()

        best = _state["best_mean_seen"]
        if best is not None and quick_mean < best - 2000:
            raise optuna.TrialPruned()

        # Phase 2: full eval on train pool
        remaining = n_seeds - batch_size
        if remaining > 0:
            full_results = compare(
                bot_a_path=skant_path,
                bot_b_path=skant_path,
                opponent_pool=train_pool,
                n_seeds=remaining,
                n_workers=n_workers,
                n_hands=n_hands,
                env_overrides=env_overrides,
                seed_offset=batch_size,
            )
            per_opp_means = {}
            for opp_id in train_pool:
                q = quick_results[opp_id]["a_mean"]
                f = full_results[opp_id]["a_mean"]
                per_opp_means[opp_id] = (q * batch_size + f * remaining) / n_seeds
        else:
            per_opp_means = {opp_id: quick_results[opp_id]["a_mean"]
                             for opp_id in train_pool}

        mean_perf  = sum(per_opp_means.values()) / len(per_opp_means)
        worst_perf = min(per_opp_means.values())

        if _state["best_mean_seen"] is None or mean_perf > _state["best_mean_seen"]:
            _state["best_mean_seen"] = mean_perf

        for opp_id, m in per_opp_means.items():
            trial.set_user_attr(f"train_{opp_id}_mean", m)

        # Phase 3: Evaluate on Unseen Validation pool
        unseen_results = compare(
            bot_a_path=skant_path,
            bot_b_path=skant_path,
            opponent_pool=validation_pool,
            n_seeds=n_seeds,
            n_workers=n_workers,
            n_hands=n_hands,
            env_overrides=env_overrides,
        )
        
        unseen_means = [s["a_mean"] for s in unseen_results.values()]
        unseen_mean = sum(unseen_means) / len(unseen_means) if unseen_means else 0.0

        for opp_id, res in unseen_results.items():
            trial.set_user_attr(f"unseen_{opp_id}_mean", res["a_mean"])

        trial.set_user_attr("unseen_mean", unseen_mean)

        return mean_perf, worst_perf, unseen_mean

    return objective

def parse_pool_arg(arg: str) -> dict:
    if "::" in arg:
        module_path, attr_name = arg.split("::")
        # Load from module
        mod_name = module_path.replace("/", ".").replace(".py", "")
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr_name)
    else:
        # Load JSON
        return json.loads(Path(arg).read_text())

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_sweep(
    n_trials:    int,
    n_seeds:     int,
    n_hands:     int,
    n_workers:   int,
    batch_size:  int,
    study_name:  str,
    storage:     str,
    train_opponents: str,
    validation_opponents: str,
    worst_case_floor: float,
    resume:      bool = False,
) -> "optuna.Study":
    import optuna
    from harness.opponents.registry import SKANTBOT_TUNABLE_PATH, validate_pool

    train_pool = parse_pool_arg(train_opponents)
    validate_pool(train_pool)
    
    validation_pool = parse_pool_arg(validation_opponents)
    validate_pool(validation_pool)

    _RESULTS_DIR.mkdir(exist_ok=True)
    if storage is None:
        storage = f"sqlite:///{_RESULTS_DIR}/sweep_{study_name}.db"

    sampler = optuna.samplers.TPESampler(seed=42)
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        sampler=sampler,
        directions=["maximize", "maximize", "maximize"],   # mean_perf, worst_perf, unseen_mean
        load_if_exists=resume,
    )

    objective = make_objective(
        train_pool=train_pool,
        validation_pool=validation_pool,
        skant_path=SKANTBOT_TUNABLE_PATH,
        n_seeds=n_seeds,
        n_hands=n_hands,
        n_workers=n_workers,
        batch_size=batch_size,
    )

    print(f"=== Optuna Sweep: {study_name} ===")
    print(f"Tuning {len(PARAM_SPACE)} parameters over {len(train_pool)} train and {len(validation_pool)} unseen opponents")
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
    print(f"{'Trial':>6} {'Train Mean':>12} {'Train Worst':>12} {'Unseen Mean':>12}")
    print("-" * 47)
    for t in sorted(pareto, key=lambda t: -t.values[0]):
        print(f"{t.number:>6} {t.values[0]:>+12.1f} {t.values[1]:>+12.1f} {t.values[2]:>+12.1f}")

    # Save best config (hard floor on worst performance)
    survivors = [t for t in pareto if t.values[1] >= worst_case_floor]
    if not survivors:
        best_worst = max(t.values[1] for t in pareto) if pareto else float('-inf')
        raise ValueError(
            f"No trial achieved worst_perf >= {worst_case_floor}. "
            f"Best worst_perf was {best_worst:.1f}."
        )
        
    # Maximize the absolute profit across both training and unseen pools
    best = max(survivors, key=lambda t: t.values[0] + t.values[2])
    best_path = _RESULTS_DIR / f"best_params_{study_name}.json"
    best_path.write_text(json.dumps({
        "trial_number": best.number,
        "train_mean":   best.values[0],
        "train_worst":  best.values[1],
        "unseen_mean":  best.values[2],
        "params":       best.params,
        "env_vars":     {f"SKANT_{k.upper()}": str(v)
                         for k, v in best.params.items()},
    }, indent=2))
    print(f"\nBest params saved (optimizing for unseen generalization): {best_path}")

    return study


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Optuna sweep for skantbot4")
    p.add_argument("--trials",      type=int, default=1500)
    p.add_argument("--seeds",       type=int, default=40)
    p.add_argument("--hands",       type=int, default=200)
    p.add_argument("--workers",     type=int, default=16)
    p.add_argument("--batch-size",  type=int, default=10,
                   help="Seeds per pruning batch (default: 10)")
    p.add_argument("--study-name",  default="skantbot6_generalisation_sweep")
    p.add_argument("--storage",     default=None)
    
    # New args
    p.add_argument("--train-opponents", default="harness/opponents/registry.py::TRAIN_EXPANDED")
    p.add_argument("--validation-opponents", default="harness/opponents/registry.py::UNSEEN_VALIDATION")
    p.add_argument("--multi-objective", nargs="+", default=["train_mean", "train_worst_case", "unseen_mean"])
    p.add_argument("--worst-case-floor", type=float, default=-3000)

    p.add_argument("--resume",      action="store_true")
    args = p.parse_args()
    
    run_sweep(
        n_trials=args.trials,
        n_seeds=args.seeds,
        n_hands=args.hands,
        n_workers=args.workers,
        batch_size=args.batch_size,
        study_name=args.study_name,
        storage=args.storage,
        train_opponents=args.train_opponents,
        validation_opponents=args.validation_opponents,
        worst_case_floor=args.worst_case_floor,
        resume=args.resume,
    )
