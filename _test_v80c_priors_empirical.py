"""Empirical test of V80c priors: for each candidate override, run paired-diff
against 7.13 baseline on heldout pool. The override that improves heldout most
without breaking train is the direction.

This replaces ineffective paper hands with actual chip measurements.
"""
import sys, os, importlib.util
sys.path.insert(0, ".")
from harness.match_runner import compare, aggregate_by_opponent
from harness.opponents.registry import load_pool

OVERRIDES = {
    "B_eq_call_up":   {"equity_call_threshold": 0.45},
    "C_thin_up":      {"equity_thin_value": 0.55},
    "D_bluff_dn":     {"bluff_freq_oop": 0.02},
    "E_pot_buf_up":   {"pot_odds_buffer_normal": 0.15},
    "F_k_commit_dn":  {"k_commit": 0.001},
    "G_combined":     {
        "equity_call_threshold": 0.45,
        "equity_thin_value": 0.55,
        "bluff_freq_oop": 0.02,
        "pot_odds_buffer_normal": 0.15,
        "k_commit": 0.001,
    },
}


if __name__ == "__main__":
    train = load_pool(include_heldout=False)
    held = load_pool(include_heldout=True)
    heldout_only = {k: v for k, v in held.items() if k not in train}

    print(f"Heldout pool: {len(heldout_only)} opps")
    print(f"\nAbsolute-mean comparison: 7.13 baseline mean vs 7.13+override mean.")
    print(f"NEGATIVE Δ = override LOST chips. POSITIVE Δ = override GAINED chips.\n")

    # Baseline first
    print(f"--- A_baseline (no overrides) ---", flush=True)
    res_baseline = compare(
        bot_a_path="harness/skantbot7_13_dev/bot.py",
        bot_b_path="harness/skantbot7_13_dev/bot.py",
        opponent_pool=heldout_only,
        n_seeds=20, n_workers=2, n_hands=400,
        show_progress=False, mode="6max", n_tables=10,
        env_overrides=None,
    )
    agg_b = aggregate_by_opponent(res_baseline)
    baseline_mean = sum(s.get("a_mean", 0) for s in agg_b.values())
    baseline_se = (sum(s.get("a_stderr", 0)**2 for s in agg_b.values()))**0.5
    print(f"  Heldout pool sum: {baseline_mean:+.0f} ± {baseline_se:.0f}\n", flush=True)

    results = {"A_baseline": (baseline_mean, baseline_se, 0)}
    for name, overrides in OVERRIDES.items():
        env = {f"SKANT_{k.upper()}": str(v) for k, v in overrides.items()}
        print(f"--- {name}: {overrides} ---", flush=True)
        res = compare(
            bot_a_path="harness/skantbot7_13_dev/bot.py",
            bot_b_path="harness/skantbot7_13_dev/bot.py",
            opponent_pool=heldout_only,
            n_seeds=20, n_workers=2, n_hands=400,
            show_progress=False, mode="6max", n_tables=10,
            env_overrides=env,
        )
        agg = aggregate_by_opponent(res)
        mean = sum(s.get("a_mean", 0) for s in agg.values())
        se = (sum(s.get("a_stderr", 0)**2 for s in agg.values()))**0.5
        delta = mean - baseline_mean
        results[name] = (mean, se, delta)
        print(f"  Heldout pool sum: {mean:+.0f} ± {se:.0f}, Δ vs baseline: {delta:+.0f}\n", flush=True)

    print("=" * 78)
    print("SUMMARY — sorted by Δ (positive = override IMPROVES heldout mean)")
    print("=" * 78)
    for name, (mean, se, delta) in sorted(results.items(), key=lambda x: -x[1][2]):
        verdict = "✓ IMPROVES" if delta > 300 else "~NEUTRAL" if delta > -300 else "✗ HURTS"
        print(f"  {name:<18}  mean={mean:+6.0f} ± {se:.0f}  Δ={delta:+6.0f}  {verdict}")
