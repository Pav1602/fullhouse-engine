"""Analyze the V80b sweep DB to answer:

1. Are we converging? (objective values over trial number)
2. What are the best trials by each objective?
3. Did key params move in the expected directions vs the 7.13 anchor?
4. Is the Pareto front populated with diverse solutions?

Run after: rsync the latest DB snapshot into harness/results/.
"""
import sys, sqlite3, json
from collections import defaultdict
sys.path.insert(0, ".")

import optuna

DB = "harness/results/sweep_db_snapshots/skb80b_1030.db"

# Expected directions per V80b priors (1 = ↑ / -1 = ↓ / 0 = neutral)
EXPECTED = {
    "equity_call_threshold":      +1,   # tighter postflop calling, close hero-call leak
    "pot_odds_buffer_normal":     +1,   # more eq required vs pot odds
    "cbet_freq_base":             -1,   # Mode A reduction
    "bluff_freq_ip":              -1,   # Mode A reduction
    "bluff_freq_oop":             -1,   # Mode A reduction
    "threebet_call_threshold_pct":-1,   # tighter preflop defense
    "fourbet_call_threshold_pct": -1,   # tighter preflop defense
    "k_commit":                   -1,   # less aggressive commitment
    "small_open_call_boost":      -1,   # less defending small opens
    "fourbet_bluff_freq":         -1,   # Mode A reduction
}


def main():
    study = optuna.load_study(study_name="skb80b", storage=f"sqlite:///{DB}")
    trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    print(f"Loaded {len(trials)} complete trials from {DB}")
    print(f"Directions: {study.directions}")
    print()

    if not trials:
        print("No complete trials yet."); return

    n_obj = len(trials[0].values) if trials[0].values else 0
    obj_names = ["train_mean", "train_worst", "unseen_mean", "hu_polished_mean"][:n_obj]

    # === 1. Convergence: best-so-far for each objective over trial number ===
    print("=" * 72)
    print("1. CONVERGENCE — best-so-far for each objective")
    print("=" * 72)
    best_so_far = [[-1e18]*n_obj for _ in range(len(trials))]
    for i, t in enumerate(trials):
        if i == 0:
            best_so_far[0] = list(t.values)
        else:
            best_so_far[i] = [max(best_so_far[i-1][j], t.values[j]) for j in range(n_obj)]
    # Sample every 100 trials
    print(f"{'trial':>6}  " + "  ".join(f"{n:>14}" for n in obj_names))
    for i in [0, 99, 199, 299, 499, 699, 899, len(trials)-1]:
        if i >= len(trials): continue
        print(f"{trials[i].number:>6}  " + "  ".join(f"{best_so_far[i][j]:>14.1f}" for j in range(n_obj)))
    print()

    # === 2. Top trials per objective ===
    print("=" * 72)
    print("2. TOP 5 BY EACH OBJECTIVE")
    print("=" * 72)
    for j, name in enumerate(obj_names):
        print(f"\n--- by {name} (objective {j}) ---")
        top = sorted(trials, key=lambda t: -t.values[j])[:5]
        for t in top:
            vals = "  ".join(f"{n}={v:+.0f}" for n, v in zip(obj_names, t.values))
            print(f"  #{t.number:<5}  {vals}")

    # === 3. Pareto front ===
    print()
    print("=" * 72)
    print("3. PARETO FRONT")
    print("=" * 72)
    pareto = study.best_trials
    print(f"{len(pareto)} Pareto-optimal solutions")
    if pareto:
        print(f"\nSample Pareto front (first 10):")
        print(f"{'trial':>6}  " + "  ".join(f"{n:>14}" for n in obj_names))
        for t in sorted(pareto, key=lambda x: -x.values[0])[:10]:
            print(f"{t.number:>6}  " + "  ".join(f"{t.values[j]:>14.1f}" for j in range(n_obj)))

    # === 4. Direction check ===
    print()
    print("=" * 72)
    print("4. PARAM DIRECTION CHECK — top 20 trials by train_mean vs 7.13 anchor")
    print("=" * 72)
    anchor = next((t for t in trials if t.number == 0), None)
    if not anchor:
        print("No anchor (trial 0) found!"); return

    top20 = sorted(trials, key=lambda t: -t.values[0])[:20]
    print(f"\nLegend: ✓ = mean of top 20 moved in expected direction; ✗ = wrong way; ≈ = no signal")
    print()
    print(f"{'param':<35} {'expect':>7} {'anchor':>10} {'top20_mean':>12} {'top5_mean':>12} {'verdict':>8}")
    print("-" * 95)
    for name, expect in EXPECTED.items():
        if name not in anchor.params: continue
        a = anchor.params[name]
        top20_vals = [t.params[name] for t in top20 if name in t.params]
        top5_vals = [t.params[name] for t in top20[:5] if name in t.params]
        top20_mean = sum(top20_vals) / max(1, len(top20_vals))
        top5_mean = sum(top5_vals) / max(1, len(top5_vals))
        diff20 = top20_mean - a
        if abs(diff20) < 0.001 * abs(a) + 0.001:
            verdict = "≈"
        elif (diff20 > 0 and expect == +1) or (diff20 < 0 and expect == -1):
            verdict = "✓"
        else:
            verdict = "✗"
        arrow = "↑" if expect == 1 else "↓"
        print(f"{name:<35} {arrow:>7} {a:>10.4f} {top20_mean:>12.4f} {top5_mean:>12.4f} {verdict:>8}")

    # === 5. Are we still improving? slope over recent trials ===
    print()
    print("=" * 72)
    print("5. ARE WE STILL IMPROVING? (objective 0 = train_mean)")
    print("=" * 72)
    for span in [100, 200, 500]:
        if len(trials) < span: continue
        recent = trials[-span:]
        first_quarter = sum(t.values[0] for t in recent[:span//4]) / (span//4)
        last_quarter = sum(t.values[0] for t in recent[-span//4:]) / (span//4)
        delta = last_quarter - first_quarter
        print(f"  Last {span} trials: train_mean shifted by {delta:+.1f}  "
              f"(first {span//4}: {first_quarter:.1f} → last {span//4}: {last_quarter:.1f})")

    # === 6. Best single trial overall ===
    print()
    print("=" * 72)
    print("6. BEST SINGLE TRIAL (by train_mean)")
    print("=" * 72)
    best = max(trials, key=lambda t: t.values[0])
    print(f"\nTrial #{best.number}:")
    for j, n in enumerate(obj_names):
        print(f"  {n}: {best.values[j]:+.1f}")
    print(f"\n  vs anchor (7.13 defaults):")
    for j, n in enumerate(obj_names):
        if anchor.values:
            d = best.values[j] - anchor.values[j]
            print(f"    {n}: anchor={anchor.values[j]:+.1f}  best={best.values[j]:+.1f}  Δ={d:+.1f}")


if __name__ == "__main__":
    main()
