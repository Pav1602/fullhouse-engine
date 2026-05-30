"""V81 sweep — focused single-scalar objective, post-step-1-only param space.

Scoped for the 1-week timeline:
  - 14 focused params (drops V80b's noise dimensions; #2 modifier excluded
    because Step 2 was rolled back as misclassifying LLM tight-folders)
  - Single-scalar weighted objective: 0.4 * train_mean + 0.6 * min(heldout)
    forces TPE to find solutions where NO heldout opp regresses badly
    (V80b's failure mode was Pareto with mean letting one opp tank)
  - TPE sampler, seed=42
  - Anchor trial 0 with the current skantbot8 (= 7.13 + #1) defaults so
    later trials are evaluated relative to a known baseline.

Usage:
    python _sweep_v81.py [n_trials=200] [n_seeds=20] [n_tables=15] [n_workers=24]
"""
import sys, json, time
sys.path.insert(0, ".")

N_TRIALS = int(sys.argv[1]) if len(sys.argv) > 1 else 200
N_SEEDS = int(sys.argv[2]) if len(sys.argv) > 2 else 20
N_TABLES = int(sys.argv[3]) if len(sys.argv) > 3 else 15
N_WORKERS = int(sys.argv[4]) if len(sys.argv) > 4 else 24
N_HANDS = 200
STUDY_NAME = "skb8_v81"
STORAGE = f"sqlite:///harness/results/{STUDY_NAME}.db"
SKANT_DEV = "harness/skantbot8_dev/bot.py"


# ---------------------------------------------------------------------------
# Param space — 14 focused params. NO #2 narrowing params (rejected).
# NO 12 dead params from advisor amendment.
# ---------------------------------------------------------------------------
PARAM_SPACE_V81 = {
    # Confirmed-direction equity / pot-odds knobs (V80b 1D sweeps showed signal)
    "equity_call_threshold":         ("float", 0.35, 0.50),
    "pot_odds_buffer_normal":        ("float", 0.08, 0.18),
    "equity_thin_value":             ("float", 0.40, 0.55),

    # Bluff / cbet frequencies — dominant effect on aggression-vs-folder pools
    "bluff_freq_ip":                 ("float", 0.01, 0.06),
    "bluff_freq_oop":                ("float", 0.01, 0.05),
    "cbet_freq_base":                ("float", 0.50, 0.70),

    # Preflop call thresholds
    "threebet_call_threshold_pct":   ("float", 0.10, 0.22),
    "fourbet_call_threshold_pct":    ("float", 0.08, 0.14),
    "fourbet_bluff_freq":            ("float", 0.05, 0.30),

    # Commit / sizing knobs
    "k_commit":                      ("float", 0.0, 0.012),
    "river_v2b_half_pot":            ("float", 1.5, 3.0),

    # V81 #1: RELATIVE multiplier (absolute version was rejected at 7.14)
    "skb8_bet_to_mean_multiplier":   ("float", 1.2, 2.0),
    "skb8_min_obs_for_signal":       ("int",   15,  50),
    "skb8_min_bets_obs_for_signal":  ("int",   3,   10),
}

# Current skantbot8 defaults (= 7.13 + #1) — trial 0 anchor.
ANCHOR_TRIAL = {
    "equity_call_threshold": 0.3919811186191172,
    "pot_odds_buffer_normal": 0.1014539537201927,
    "equity_thin_value": 0.4770665192555191,
    "bluff_freq_ip": 0.05223860805977661,
    "bluff_freq_oop": 0.03942295665836069,
    "cbet_freq_base": 0.6359670747418533,
    "threebet_call_threshold_pct": 0.2170225254829958,
    "fourbet_call_threshold_pct": 0.1351630858370252,
    "fourbet_bluff_freq": 0.30,
    "k_commit": 0.005431736240613369,
    "river_v2b_half_pot": 2.0,  # NB. value preserved
    "skb8_bet_to_mean_multiplier": 1.5,
    "skb8_min_obs_for_signal": 30,
    "skb8_min_bets_obs_for_signal": 5,
}


def main():
    import optuna
    from harness.match_runner import compare, aggregate_by_opponent
    from harness.opponents.registry import (
        TRAIN_EXPANDED_V81, UNSEEN_VALIDATION_V81,
    )

    train_pool = dict(TRAIN_EXPANDED_V81)
    heldout_pool = dict(UNSEEN_VALIDATION_V81)
    print(f"Train pool: {len(train_pool)} opps")
    print(f"Heldout pool: {len(heldout_pool)} opps")
    print(f"Params: {len(PARAM_SPACE_V81)}")
    print(f"Trials: {N_TRIALS}, seeds: {N_SEEDS}, n_tables: {N_TABLES}")
    print()

    def objective(trial):
        # Build env overrides.
        params = {}
        for name, (dtype, lo, hi) in PARAM_SPACE_V81.items():
            if dtype == "float":
                params[name] = trial.suggest_float(name, lo, hi)
            else:
                params[name] = trial.suggest_int(name, int(lo), int(hi))
        env = {f"SKANT_{k.upper()}": str(v) for k, v in params.items()}

        t0 = time.time()
        # Train phase
        train_res = compare(
            bot_a_path=SKANT_DEV, bot_b_path=SKANT_DEV,
            opponent_pool=train_pool,
            n_seeds=N_SEEDS, n_workers=N_WORKERS, n_hands=N_HANDS,
            env_overrides=env, mode="6max", n_tables=N_TABLES,
            show_progress=False,
        )
        agg_train = aggregate_by_opponent(train_res)
        train_means = [s["a_mean"] for s in agg_train.values()]
        train_mean = sum(train_means) / max(len(train_means), 1)
        train_worst = min(train_means) if train_means else 0.0

        # Heldout phase
        held_res = compare(
            bot_a_path=SKANT_DEV, bot_b_path=SKANT_DEV,
            opponent_pool=heldout_pool,
            n_seeds=N_SEEDS, n_workers=N_WORKERS, n_hands=N_HANDS,
            env_overrides=env, mode="6max", n_tables=N_TABLES,
            show_progress=False,
        )
        agg_held = aggregate_by_opponent(held_res)
        held_means = [s["a_mean"] for s in agg_held.values()]
        held_min = min(held_means) if held_means else 0.0
        held_mean = sum(held_means) / max(len(held_means), 1)

        # Single-scalar objective per V81 plan §8.2.
        score = 0.4 * train_mean + 0.6 * held_min
        trial.set_user_attr("train_mean", train_mean)
        trial.set_user_attr("train_worst", train_worst)
        trial.set_user_attr("held_mean", held_mean)
        trial.set_user_attr("held_min", held_min)
        trial.set_user_attr("seconds", round(time.time() - t0, 2))
        for opp, stats in agg_held.items():
            trial.set_user_attr(f"held_{opp}_mean", stats["a_mean"])
        return score

    sampler = optuna.samplers.TPESampler(seed=42)
    study = optuna.create_study(
        study_name=STUDY_NAME, storage=STORAGE,
        direction="maximize", sampler=sampler, load_if_exists=True,
    )
    if len(study.trials) == 0:
        anchor = {k: v for k, v in ANCHOR_TRIAL.items() if k in PARAM_SPACE_V81}
        study.enqueue_trial(anchor)
        print(f"Enqueued anchor trial: {len(anchor)}/{len(PARAM_SPACE_V81)} params")

    n_done = len(study.trials)
    print(f"Resuming from {n_done} existing trials. Target: {N_TRIALS}")
    study.optimize(objective, n_trials=max(N_TRIALS - n_done, 1),
                   show_progress_bar=False)

    print("\n=== Best trial ===")
    bt = study.best_trial
    print(f"  score: {bt.value:.2f}")
    print(f"  train_mean: {bt.user_attrs.get('train_mean'):.0f}")
    print(f"  held_min: {bt.user_attrs.get('held_min'):.0f}")
    print(f"  held_mean: {bt.user_attrs.get('held_mean'):.0f}")
    print(f"  params:")
    for k, v in sorted(bt.params.items()):
        print(f"    {k} = {v}")

    out_path = f"harness/results/sweep_v81_best.json"
    with open(out_path, "w") as f:
        json.dump({
            "best_score": bt.value,
            "best_params": bt.params,
            "user_attrs": dict(bt.user_attrs),
            "n_trials": len(study.trials),
        }, f, indent=2, default=str)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
