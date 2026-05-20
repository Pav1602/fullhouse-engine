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
    "cbet_freq_base": ("float", 0.30, 0.668),
    "bluff_freq_ip": ("float", 0.005, 0.056),
    "bluff_freq_oop": ("float", 0.01, 0.101),
    "k_texture_paired": ("float", 0.10, 0.50),
    "k_texture_connected": ("float", -0.30, 0.10),
    "equity_call_threshold": ("float", 0.35, 0.60),
    "pot_odds_buffer_normal": ("float", 0.05, 0.20),
    "variance_c": ("float", 0.005, 0.10),
    "equity_value_bet": ("float", 0.55, 0.75),
    "equity_thin_value": ("float", 0.45, 0.62),
}

# ---------------------------------------------------------------------------
# Optuna objective
# ---------------------------------------------------------------------------

def make_objective(
    train_pool: dict,
    mode: str,
    n_tables: int,
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
            mode=mode,
            n_tables=n_tables,
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
                mode=mode,
                n_tables=n_tables,
            )
            merged_results = {}
            for k in quick_results.keys():
                q = quick_results[k]
                f = full_results.get(k, q)
                n_q = q["n"]
                n_f = f["n"] if k in full_results else 0
                total_n = n_q + n_f
                merged_a_mean = (q["a_mean"] * n_q + f["a_mean"] * n_f) / total_n if total_n > 0 else 0.0
                merged_results[k] = {"a_mean": merged_a_mean, "opponents": q.get("opponents", [])}
        else:
            merged_results = quick_results

        table_means = [v["a_mean"] for v in merged_results.values()]
        mean_perf  = sum(table_means) / len(table_means) if table_means else 0.0
        worst_perf = min(table_means) if table_means else 0.0

        if _state["best_mean_seen"] is None or mean_perf > _state["best_mean_seen"]:
            _state["best_mean_seen"] = mean_perf

        if mode == "6max":
            from harness.match_runner import aggregate_by_opponent
            agg_train = aggregate_by_opponent(merged_results)
            for opp_id, stat in agg_train.items():
                trial.set_user_attr(f"opp_{opp_id}_mean", stat["a_mean"])
        else:
            for opp_id, v in merged_results.items():
                trial.set_user_attr(f"opp_{opp_id}_mean", v["a_mean"])

        # Phase 3: Evaluate on Unseen Validation pool
        unseen_results = compare(
            bot_a_path=skant_path,
            bot_b_path=skant_path,
            opponent_pool=validation_pool,
            n_seeds=n_seeds,
            n_workers=n_workers,
            n_hands=n_hands,
            env_overrides=env_overrides,
            mode=mode,
            n_tables=n_tables,
        )
        
        unseen_table_means = [s["a_mean"] for s in unseen_results.values()]
        unseen_mean = sum(unseen_table_means) / len(unseen_table_means) if unseen_table_means else 0.0

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
    mode: str,
    n_tables: int,
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
        mode=mode,
        n_tables=n_tables,
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
    p.add_argument("--mode", default="6max", choices=["hu", "6max"])
    p.add_argument("--n-tables", type=int, default=10)
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
        mode=args.mode,
        n_tables=args.n_tables,
        study_name=args.study_name,
        storage=args.storage,
        train_opponents=args.train_opponents,
        validation_opponents=args.validation_opponents,
        worst_case_floor=args.worst_case_floor,
        resume=args.resume,
    )
