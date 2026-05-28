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
import multiprocessing
from pathlib import Path

# Force spawn start method to avoid fork+SQLite-mutex deadlock when
# Optuna's joblib backend runs n_jobs>1 with the harness's compare()
# (which itself spawns multiprocessing pool + sandbox subprocesses).
# Without this, n_jobs>1 deadlocks at 100% CPU idle on cloud instances.
# Must be called before any other multiprocessing-using code.
try:
    multiprocessing.set_start_method('spawn', force=True)
except RuntimeError:
    pass  # already set

_REPO_ROOT = str(Path(__file__).parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_RESULTS_DIR = Path(__file__).parent / "results"

# ---------------------------------------------------------------------------
# Parameter search space — legacy (v75/v76) 10-param set
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
# v79 PARAM_SPACE — 42 params, post-parser-fix re-tune
# ---------------------------------------------------------------------------
# Built 2026-05-23 after the silent chart-expansion bug fix shipped as 7.8.
# Goal: re-tune thresholds that compensated for the broken BB-defending
# charts. Sibling-coherence groups (k_texture_*, k_bluff_vs_*_folder,
# standing_alpha/beta) tuned jointly to avoid one-sided re-tuning.
# See PLAN_7.8_parser_fix.md and project_parser_bug_range_hyphen memory.
# === V80 directional priors (from 7.11 bust survey, 200 matches) ===
# 1. Preflop defense should tighten (60%+ of bust $ traces to wide 3-bet
#    defense). Sweep these UPWARD (tighter):
#      threebet_call_threshold_pct  : current default ~0.22, try 0.10-0.20
#      fourbet_call_threshold_pct   : current default ~0.135, try 0.08-0.13
#      small_open_call_boost        : current default ~1.7, try 1.0-1.5
# 2. Postflop calling should tighten on wet boards:
#      equity_call_threshold        : sweep 0.42-0.55 (currently 0.39)
#      pot_odds_buffer_normal       : sweep 0.10-0.18 (currently 0.10)
# 3. Mode A cbet/bluff (known-since-7.4 issue):
#      cbet_freq_base               : sweep DOWN 0.40-0.55 (currently 0.64)
#      bluff_freq_ip                : sweep DOWN 0.02-0.05 (currently 0.05)
#      bluff_freq_oop               : sweep DOWN 0.01-0.03 (currently 0.04)
# 4. New 7.11 Phase 2a knobs (just added, default-only validated):
#      committed_pot_ratio          : sweep 0.4-1.0
#      phase2a_baseline             : sweep 0.10-0.25
#      phase2a_denominator          : sweep 0.50-1.20

PARAM_SPACE_V79 = {
    # --- A. Preflop tightness (8) — directly disrupted by parser fix ---
    "rfi_tightness":                ("float", 1.0, 1.6),
    "threebet_tightness":           ("float", 0.7, 1.3),
    "fourbet_tightness":            ("float", 0.9, 1.5),
    "threebet_call_threshold_pct":  ("float", 0.10, 0.30),
    "fourbet_call_threshold_pct":   ("float", 0.10, 0.25),
    "small_open_threshold_bb":      ("float", 1.5, 3.0),
    "small_open_call_boost":        ("float", 1.5, 3.0),
    "small_open_3bet_boost":        ("float", 1.2, 2.5),

    # --- B. Stack curve (2) ---
    "shrink_widening_factor":  ("float", 0.0, 0.15),
    "stack_short_tightness":   ("float", 0.6, 1.0),

    # --- C. Postflop equity thresholds (6) ---
    "equity_value_bet":         ("float", 0.55, 0.75),
    "equity_thin_value":        ("float", 0.45, 0.62),
    "equity_call_threshold":    ("float", 0.35, 0.55),
    "equity_raise_threshold":   ("float", 0.75, 0.90),
    "pot_odds_buffer_normal":   ("float", 0.05, 0.20),
    "pot_odds_buffer_marginal": ("float", 0.10, 0.30),

    # --- D. Stack-risk / variance (3) ---
    "variance_c":                ("float", 0.005, 0.10),
    "stack_risk_high_eq_normal": ("float", 0.65, 0.85),
    "stack_risk_med_eq_normal":  ("float", 0.40, 0.60),

    # --- E. C-bet / bluff (6) + texture-coef siblings (3) = 9 ---
    "cbet_freq_base":         ("float", 0.40, 0.80),
    "cbet_size_pct":          ("float", 0.40, 0.70),
    "cbet_multiway_penalty":  ("float", 0.40, 0.80),
    "bluff_freq_ip":          ("float", 0.005, 0.10),
    "bluff_freq_oop":         ("float", 0.01, 0.15),
    "k_texture_paired":       ("float", 0.05, 0.40),
    "k_texture_monotone":     ("float", 0.05, 0.30),
    "k_texture_connected":    ("float", -0.30, 0.10),
    "k_texture_high_card":    ("float", -0.20, 0.10),

    # --- F. Opponent-exploit knobs (5) + barrel/wtsd siblings (3) = 8 ---
    "k_bluff_vs_cbet_folder":         ("float", 0.0, 0.7),
    "k_bluff_vs_2barrel_folder":      ("float", 0.0, 0.5),
    "k_bluff_vs_3barrel_folder":      ("float", 0.0, 0.5),
    "k_bluff_vs_wtsd":                ("float", 0.0, 0.30),
    "k_value_size_vs_station":        ("float", 0.0, 0.40),
    "k_tightness_vs_3bet_freq":       ("float", 0.0, 0.30),
    "k_4bet_vs_3bet_freq":            ("float", 0.0, 0.50),
    "k_call_threshold_vs_aggression": ("float", 0.0, 0.50),

    # --- G. River + match-state (4) + standing_alpha/beta siblings (2) = 6 ---
    "river_mdf_aggression":         ("float", 0.80, 1.20),
    "river_value_thin_threshold":   ("float", 0.50, 0.65),
    "river_value_strong_threshold": ("float", 0.72, 0.85),
    "k_standing":                   ("float", 0.10, 0.50),
    "standing_alpha":               ("float", 0.02, 0.20),
    "standing_beta":                ("float", 0.05, 0.40),
}
assert len(PARAM_SPACE_V79) == 42, f"PARAM_SPACE_V79 has {len(PARAM_SPACE_V79)} params, expected 42"

# ---------------------------------------------------------------------------
# v80 PARAM_SPACE — 45 params, post-7.12 re-tune with directional priors
# ---------------------------------------------------------------------------
# Built 2026-05-28 on top of skantbot7.12. Strategy: keep V79 architecture,
# tighten bounds where the 7.11 bust survey gave directional evidence, and
# add the 3 new Phase 2a knobs introduced in 7.11/7.12.
#
# Directional priors applied (vs V79):
#   - Preflop defense: tighter (closes the bust_195 family)
#       threebet_call_threshold_pct  0.10-0.30 → 0.10-0.22
#       fourbet_call_threshold_pct   0.10-0.25 → 0.08-0.14
#       small_open_call_boost        1.5-3.0   → 1.0-1.8
#   - Postflop calling: tighter
#       equity_call_threshold        0.35-0.55 → 0.39-0.55
#       pot_odds_buffer_normal       0.05-0.20 → 0.10-0.20
#   - Mode A cbet/bluff: lower
#       cbet_freq_base               0.40-0.80 → 0.40-0.60
#       bluff_freq_ip                0.005-0.10 → 0.005-0.06
#       bluff_freq_oop               0.01-0.15  → 0.01-0.05
#   - New Phase 2a knobs (default-only validated in 7.12):
#       committed_pot_ratio          (new) 0.4-1.0
#       phase2a_baseline             (new) 0.10-0.25
#       phase2a_denominator          (new) 0.50-1.20
PARAM_SPACE_V80 = {
    # --- A. Preflop tightness (8) — bounds tightened per priors ---
    "rfi_tightness":                ("float", 1.0, 1.6),
    "threebet_tightness":           ("float", 0.7, 1.3),
    "fourbet_tightness":            ("float", 0.9, 1.5),
    "threebet_call_threshold_pct":  ("float", 0.10, 0.22),   # TIGHTENED (was 0.10-0.30)
    "fourbet_call_threshold_pct":   ("float", 0.08, 0.14),   # TIGHTENED (was 0.10-0.25)
    "small_open_threshold_bb":      ("float", 1.5, 3.0),
    "small_open_call_boost":        ("float", 1.0, 1.8),     # SHIFTED DOWN (was 1.5-3.0)
    "small_open_3bet_boost":        ("float", 1.2, 2.5),

    # --- B. Stack curve (2) ---
    "shrink_widening_factor":  ("float", 0.0, 0.15),
    "stack_short_tightness":   ("float", 0.6, 1.0),

    # --- C. Postflop equity thresholds (6) — call thresh tightened ---
    "equity_value_bet":         ("float", 0.55, 0.75),
    "equity_thin_value":        ("float", 0.45, 0.62),
    "equity_call_threshold":    ("float", 0.39, 0.55),       # LOWER BOUND RAISED (was 0.35)
    "equity_raise_threshold":   ("float", 0.75, 0.90),
    "pot_odds_buffer_normal":   ("float", 0.10, 0.20),       # LOWER BOUND RAISED (was 0.05)
    "pot_odds_buffer_marginal": ("float", 0.10, 0.30),

    # --- D. Stack-risk / variance (3) ---
    "variance_c":                ("float", 0.005, 0.10),
    "stack_risk_high_eq_normal": ("float", 0.65, 0.85),
    "stack_risk_med_eq_normal":  ("float", 0.40, 0.60),

    # --- E. C-bet / bluff (6) + texture-coef siblings (3) = 9 — Mode A down ---
    "cbet_freq_base":         ("float", 0.40, 0.70),         # widened to include 7.13 default 0.636 (was 0.40-0.80 in V79)
    "cbet_size_pct":          ("float", 0.40, 0.70),
    "cbet_multiway_penalty":  ("float", 0.40, 0.80),
    "bluff_freq_ip":          ("float", 0.005, 0.06),        # UPPER LOWERED (was 0.10)
    "bluff_freq_oop":         ("float", 0.01, 0.05),         # UPPER LOWERED (was 0.15)
    "k_texture_paired":       ("float", 0.05, 0.40),
    "k_texture_monotone":     ("float", 0.05, 0.30),
    "k_texture_connected":    ("float", -0.30, 0.10),
    "k_texture_high_card":    ("float", -0.20, 0.10),

    # --- F. Opponent-exploit knobs (5) + barrel/wtsd siblings (3) = 8 ---
    "k_bluff_vs_cbet_folder":         ("float", 0.0, 0.7),
    "k_bluff_vs_2barrel_folder":      ("float", 0.0, 0.5),
    "k_bluff_vs_3barrel_folder":      ("float", 0.0, 0.5),
    "k_bluff_vs_wtsd":                ("float", 0.0, 0.30),
    "k_value_size_vs_station":        ("float", 0.0, 0.40),
    "k_tightness_vs_3bet_freq":       ("float", 0.0, 0.30),
    "k_4bet_vs_3bet_freq":            ("float", 0.0, 0.50),
    "k_call_threshold_vs_aggression": ("float", 0.0, 0.50),

    # --- G. River + match-state (4) + standing_alpha/beta siblings (2) = 6 ---
    "river_mdf_aggression":         ("float", 0.80, 1.20),
    "river_value_thin_threshold":   ("float", 0.50, 0.65),
    "river_value_strong_threshold": ("float", 0.72, 0.85),
    "k_standing":                   ("float", 0.10, 0.50),
    "standing_alpha":               ("float", 0.02, 0.20),
    "standing_beta":                ("float", 0.05, 0.40),

    # --- H. NEW in 7.11/7.12 — Phase 2a un-narrowing knobs (3) ---
    "committed_pot_ratio":  ("float", 0.4, 1.0),    # NEW: pot/INITIAL_STACK gate for Phase 2a override
    "phase2a_baseline":     ("float", 0.10, 0.25),  # NEW: rwf floor below which no un-narrowing
    "phase2a_denominator":  ("float", 0.50, 1.20),  # NEW: rate at which un-narrowing scales with rwf excess

    # --- I. NEW in V80b — load-bearing params untouched in V79/V80 (15) ---
    # SPR commitment regime — directly governs hero-call thinness when "committed"
    # (k_commit applied to equity_call_threshold). Hero-call leak ($346K) traces
    # to this regime firing too aggressively or too late.
    "spr_commit_threshold": ("float", 1.5, 4.0),    # default 2.54
    "spr_smoothness":       ("float", 1.0, 4.0),    # default 2.44
    "k_commit":             ("float", 0.0, 0.02),   # default 0.005 — LOWER bound at 0 (effectively disable commitment); upper tighter than prior
    # Preflop commitment gate — bust_021 territory (6-max residual after HU fix).
    "fourbet_commit_threshold": ("float", 0.15, 0.45),  # default 0.25
    # 4-bet bluff frequency — Mode A. Default 0.30 may be too high.
    "fourbet_bluff_freq":   ("float", 0.05, 0.30),   # default 0.30
    # River value-to-bluff ratios — Mode A residual ($375K).
    "river_v2b_half_pot":   ("float", 1.0, 3.0),     # default 2.0
    "river_v2b_pot_sized":  ("float", 0.5, 2.0),     # default 1.0
    "river_v2b_overbet":    ("float", 0.2, 1.5),     # default 0.5
    "k_river_bluff_blocker": ("float", 0.0, 0.40),   # default 0.17
    # Maniac/station classification — gates a lot of downstream adjustment math.
    "maniac_vpip_threshold":  ("float", 0.35, 0.55),  # default 0.439
    "maniac_pfr_threshold":   ("float", 0.35, 0.60),  # default 0.476
    "station_vpip_threshold": ("float", 0.30, 0.50),  # default 0.384
    "station_pfr_threshold":  ("float", 0.10, 0.30),  # default 0.197
    # stack_risk_*_maniac counterparts — asymmetric tuning vs V79 normal versions.
    "stack_risk_high_eq_maniac": ("float", 0.55, 0.85),  # default 0.683
    "stack_risk_med_eq_maniac":  ("float", 0.55, 0.85),  # default 0.736
}
assert len(PARAM_SPACE_V80) == 60, f"PARAM_SPACE_V80 has {len(PARAM_SPACE_V80)} params, expected 60"

# Polished-HU opponent subset for the 4th Pareto objective.
# Selected per advisor: opponents where 7.8 regressed vs 7.7 in HU mode.
HU_POLISHED_OPPONENTS = ["gemini-1", "claude-4", "gemini-6"]

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
    param_space: dict = None,
    hu_pool: dict = None,
    hu_seeds: int = 0,
):
    """If `hu_pool` is non-empty and `hu_seeds>0`, runs a 4th-axis HU compare
    against that pool after Phase 3 and returns a 4-tuple objective. Otherwise
    returns the legacy 3-tuple."""
    import optuna
    from harness.match_runner import compare

    if param_space is None:
        param_space = PARAM_SPACE

    _state = {"best_mean_seen": None}

    def objective(trial: "optuna.Trial"):
        params = {}
        for name, (dtype, lo, hi) in param_space.items():
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

        # Pruning disabled for the v75 sweep. The Stage-B starting bot is
        # deliberately detuned (pot-odds cap applied, equity thresholds not yet
        # re-tuned), so the old absolute floor (quick_worst < -2000) pruned
        # 100% of trials. Optuna's multi-objective TPE sampler also cannot
        # build a model from a history of pruned trials. Let every trial run
        # to completion so all three objective values land in the DB; trial
        # selection happens post-hoc. quick_mean / quick_worst are kept for
        # the user_attr below.
        trial.set_user_attr("quick_mean", quick_mean)
        trial.set_user_attr("quick_worst", quick_worst)

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
                # Carry every key aggregate_by_opponent() consumes. The old
                # merge only kept a_mean; b_mean / paired_diff_mean / n were
                # dropped, which KeyError'd in the 6max aggregation path. That
                # bug was masked while pruning killed trials before Phase 2.
                merged_results[k] = {
                    "a_mean": (q["a_mean"] * n_q + f["a_mean"] * n_f) / total_n if total_n > 0 else 0.0,
                    "b_mean": (q["b_mean"] * n_q + f["b_mean"] * n_f) / total_n if total_n > 0 else 0.0,
                    "paired_diff_mean": (q["paired_diff_mean"] * n_q + f["paired_diff_mean"] * n_f) / total_n if total_n > 0 else 0.0,
                    "n": total_n,
                    "opponents": q.get("opponents", []),
                }
        else:
            merged_results = quick_results

        # mean_perf / worst_perf are computed per-OPPONENT, not per-table. A
        # per-table min saturates at -STARTING_STACK (any single felted table
        # = -10000), making worst_perf a dead constant. The per-opponent
        # aggregate mean is the meaningful per-opponent worst-case signal.
        if mode == "6max":
            from harness.match_runner import aggregate_by_opponent
            agg_train = aggregate_by_opponent(merged_results)
            for opp_id, stat in agg_train.items():
                trial.set_user_attr(f"opp_{opp_id}_mean", stat["a_mean"])
            perf_means = [stat["a_mean"] for stat in agg_train.values()]
        else:
            for opp_id, v in merged_results.items():
                trial.set_user_attr(f"opp_{opp_id}_mean", v["a_mean"])
            perf_means = [v["a_mean"] for v in merged_results.values()]

        mean_perf  = sum(perf_means) / len(perf_means) if perf_means else 0.0
        worst_perf = min(perf_means) if perf_means else 0.0

        if _state["best_mean_seen"] is None or mean_perf > _state["best_mean_seen"]:
            _state["best_mean_seen"] = mean_perf

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

        # Phase 4 (v79): HU-polished objective — keep HU performance vs the
        # bots that 7.8 regressed against (gemini-1, claude-4, gemini-6).
        # Runs HU mode at hu_seeds (typically smaller than n_seeds for cost).
        if hu_pool and hu_seeds > 0:
            hu_results = compare(
                bot_a_path=skant_path,
                bot_b_path=skant_path,
                opponent_pool=hu_pool,
                n_seeds=hu_seeds,
                n_workers=n_workers,
                n_hands=n_hands,
                env_overrides=env_overrides,
                mode="hu",
                n_tables=1,
            )
            hu_means = [s["a_mean"] for s in hu_results.values()]
            hu_polished_mean = sum(hu_means) / len(hu_means) if hu_means else 0.0
            trial.set_user_attr("hu_polished_mean", hu_polished_mean)
            for opp_id, s in hu_results.items():
                trial.set_user_attr(f"hu_{opp_id}_mean", s["a_mean"])
            return mean_perf, worst_perf, unseen_mean, hu_polished_mean

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
    param_set:   str = "legacy",
    hu_seeds:    int = 0,
    n_jobs:      int = 1,
) -> "optuna.Study":
    import optuna
    from harness.opponents.registry import SKANTBOT_TUNABLE_PATH, validate_pool, load_pool

    train_pool = parse_pool_arg(train_opponents)
    validate_pool(train_pool)

    validation_pool = parse_pool_arg(validation_opponents)
    validate_pool(validation_pool)

    # Select PARAM_SPACE variant
    if param_set == "v80":
        active_param_space = PARAM_SPACE_V80
    elif param_set == "v79":
        active_param_space = PARAM_SPACE_V79
    else:
        active_param_space = PARAM_SPACE

    # HU-polished pool: subset of training pool by id
    hu_pool = {}
    if hu_seeds > 0:
        all_pool = load_pool(include_heldout=True)
        for oid in HU_POLISHED_OPPONENTS:
            if oid in all_pool:
                hu_pool[oid] = all_pool[oid]
        if hu_pool:
            print(f"HU-polished objective enabled: {list(hu_pool.keys())} at {hu_seeds} seeds")

    _RESULTS_DIR.mkdir(exist_ok=True)
    if storage is None:
        storage = f"sqlite:///{_RESULTS_DIR}/sweep_{study_name}.db"

    # Direction count must match objective tuple length
    directions = ["maximize", "maximize", "maximize"]
    if hu_pool and hu_seeds > 0:
        directions.append("maximize")  # hu_polished_mean

    # NSGA-II is better for multi-objective; TPE for ≤3 objectives
    if len(directions) >= 4:
        sampler = optuna.samplers.NSGAIISampler(seed=42, population_size=50)
    else:
        sampler = optuna.samplers.TPESampler(seed=42)

    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        sampler=sampler,
        directions=directions,
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
        param_space=active_param_space,
        hu_pool=hu_pool,
        hu_seeds=hu_seeds,
    )

    print(f"=== Optuna Sweep: {study_name} ===")
    print(f"Tuning {len(active_param_space)} parameters over {len(train_pool)} train and {len(validation_pool)} unseen opponents")
    print(f"Trials: {n_trials}  |  Seeds/trial: {n_seeds}  |  Workers: {n_workers}  |  n_jobs (parallel trials): {n_jobs}")
    print(f"Storage: {storage}\n")

    # Enqueue current submission-bot defaults as trial 0 so TPE/NSGA-II has
    # a known-good baseline anchor. Without this, 5000 random-then-modeled
    # trials could all converge worse than the starting point. Only seeds
    # params that exist in the active space and fall within its bounds.
    if not resume:
        try:
            import importlib.util as _ilu
            from harness.opponents.registry import SKANTBOT_TUNABLE_PATH as _STP
            _spec = _ilu.spec_from_file_location("_skant_anchor", _STP)
            _m = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_m)
            _cfg = _m.CONFIG
            anchor = {}
            skipped = []
            for name, (dtype, lo, hi) in active_param_space.items():
                if hasattr(_cfg, name):
                    v = getattr(_cfg, name)
                    if lo <= v <= hi:
                        anchor[name] = v
                    else:
                        skipped.append((name, v, lo, hi))
            if skipped:
                print(f"Anchor skipped {len(skipped)} params (default outside V80 bounds):")
                for name, v, lo, hi in skipped:
                    print(f"  {name}={v}  bound=({lo}, {hi})")
            print(f"Enqueueing baseline anchor: {len(anchor)}/{len(active_param_space)} params from {_STP}")
            study.enqueue_trial(anchor)
        except Exception as _e:
            print(f"Warning: could not enqueue baseline anchor — {_e}")

    # show_progress_bar=False to avoid tqdm hijacking subprocess pipes on
    # high-fan-out cloud configs (caused total deadlock during 7.9 sweep
    # attempt on c7i.48xlarge). Progress visible via DB queries instead.
    study.optimize(
        objective,
        n_trials=n_trials,
        show_progress_bar=False,
        n_jobs=n_jobs,
    )

    # Print Pareto front (handles 3 or 4 objectives)
    pareto = study.best_trials
    n_obj = len(directions)
    print(f"\n=== Pareto Front ({len(pareto)} solutions, {n_obj} objectives) ===")
    headers = ["Trial", "Train Mean", "Train Worst", "Unseen Mean"]
    if n_obj == 4:
        headers.append("HU Polished")
    print("  ".join(f"{h:>12}" for h in headers))
    print("-" * (14 * len(headers)))
    for t in sorted(pareto, key=lambda t: -t.values[0]):
        row = [f"{t.number:>12}"] + [f"{v:>+12.1f}" for v in t.values]
        print("  ".join(row))

    # Selection: hard floor on worst_perf; if 4 objectives, also enforce
    # hu_polished_mean ≥ -SE_band relative to 7.7 baseline (sweep can't
    # know that here — caller decides post-hoc by reading best_params JSON).
    survivors = [t for t in pareto if t.values[1] >= worst_case_floor]
    if not survivors:
        best_worst = max(t.values[1] for t in pareto) if pareto else float('-inf')
        raise ValueError(
            f"No trial achieved worst_perf >= {worst_case_floor}. "
            f"Best worst_perf was {best_worst:.1f}."
        )

    # Optimize sum(train_mean + unseen_mean) — HU axis enforced at gate-time
    best = max(survivors, key=lambda t: t.values[0] + t.values[2])
    saved = {
        "trial_number": best.number,
        "train_mean":   best.values[0],
        "train_worst":  best.values[1],
        "unseen_mean":  best.values[2],
        "params":       best.params,
        "env_vars":     {f"SKANT_{k.upper()}": str(v)
                         for k, v in best.params.items()},
    }
    if n_obj == 4:
        saved["hu_polished_mean"] = best.values[3]
    best_path = _RESULTS_DIR / f"best_params_{study_name}.json"
    best_path.write_text(json.dumps(saved, indent=2))
    print(f"\nBest params saved: {best_path}")
    if n_obj == 4:
        print(f"  hu_polished_mean for best trial: {best.values[3]:+.1f}")
        print(f"  ↑ verify this is >= your 7.7 HU baseline within SE before promoting.")

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
    # v79 additions
    p.add_argument("--param-set", default="legacy", choices=["legacy", "v79", "v80"],
                   help="legacy = 10-param sweep; v79 = 42-param post-parser-fix sweep")
    p.add_argument("--hu-seeds", type=int, default=0,
                   help="If >0, adds a 4th HU-polished objective at this seed count")
    p.add_argument("--n-jobs", type=int, default=1,
                   help="Parallel trials (n_jobs * n_workers should ≤ total vCPUs)")
    args = p.parse_args()

    run_sweep(
        n_trials=args.trials,
        n_seeds=args.seeds,
        n_hands=args.hands,
        n_workers=args.workers,
        batch_size=args.batch_size,
        mode=args.mode,
        n_tables=args.n_tables,
        param_set=args.param_set,
        hu_seeds=args.hu_seeds,
        n_jobs=args.n_jobs,
        study_name=args.study_name,
        storage=args.storage,
        train_opponents=args.train_opponents,
        validation_opponents=args.validation_opponents,
        worst_case_floor=args.worst_case_floor,
        resume=args.resume,
    )
