"""Tail / variance analysis: does 7.10 have fewer catastrophic losses than 7.9?

The advisor's claim: hand-27-class busts are rare events that don't move the
mean much but show up in the left tail of the per-match chip-delta distribution.

This re-runs compare() at n=50 seeds (10 tables/seed) for both 7.9 and 7.10,
collects ALL per-table chip deltas (4 swap-variants × 50 seeds × 10 tables ×
23 opponents = ~46k matches), then compares distribution stats — std, min,
5th/10th percentile.
"""
import sys, json, numpy as np
from pathlib import Path
sys.path.insert(0, ".")
from harness.match_runner import compare
from harness.opponents.registry import load_pool


def collect(bot_path, label):
    pool = load_pool(include_heldout=False)
    print(f"\n=== Collecting per-match chip deltas for {label} ===")
    results = compare(
        bot_a_path=bot_path, bot_b_path=bot_path,
        opponent_pool=pool,
        n_seeds=50, n_workers=24, n_hands=200,
        show_progress=False, mode="6max", n_tables=10,
    )
    # results: {table_id: {a_mean, b_mean, paired_diff_mean, n, opponents, ...}}
    # a_mean is skantbot's per-table chip delta (averaged over n hands in that table).
    # Each opponent appears in many tables (random pairings).
    all_deltas = []
    for tid, data in results.items():
        all_deltas.append(data["a_mean"])
    return np.array(all_deltas)


def stats(arr, label):
    return {
        "label": label,
        "n_matches": len(arr),
        "mean": float(np.mean(arr)),
        "stderr_of_mean": float(np.std(arr, ddof=1) / np.sqrt(len(arr))),
        "std": float(np.std(arr, ddof=1)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "p5":  float(np.percentile(arr, 5)),
        "p10": float(np.percentile(arr, 10)),
        "p25": float(np.percentile(arr, 25)),
        "p50": float(np.percentile(arr, 50)),
        "p75": float(np.percentile(arr, 75)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        # Big-loss exposure: matches losing > 5000 chips (catastrophic)
        "matches_loss_gt_5k": int(np.sum(arr < -5000)),
        "matches_loss_gt_3k": int(np.sum(arr < -3000)),
        "matches_loss_gt_1k": int(np.sum(arr < -1000)),
    }


def main():
    d_09 = collect("bots/skantbot7.9/bot.py", "7.9 (pre-fix)")
    d_10 = collect("bots/skantbot7.10/bot.py", "7.10 (post-fix)")

    s9 = stats(d_09, "7.9")
    s10 = stats(d_10, "7.10")

    print()
    print("=" * 72)
    print(f"{'metric':<26} {'7.9':>14} {'7.10':>14} {'Δ':>10}")
    print("-" * 72)
    keys = ["n_matches", "mean", "stderr_of_mean", "std",
            "min", "p5", "p10", "p25", "p50", "p75", "p90", "p95", "max",
            "matches_loss_gt_5k", "matches_loss_gt_3k", "matches_loss_gt_1k"]
    for k in keys:
        v9, v10 = s9[k], s10[k]
        d = v10 - v9
        if isinstance(v9, float):
            print(f"  {k:<24} {v9:>+14.1f} {v10:>+14.1f} {d:>+10.1f}")
        else:
            print(f"  {k:<24} {v9:>14d} {v10:>14d} {d:>+10d}")

    print()
    print("=" * 72)
    print("Interpretation guide:")
    print("  - Lower std         = less variance (the bust-reduction signal)")
    print("  - Higher p5/p10     = fewer catastrophic losses (left tail thinning)")
    print("  - Fewer >5k losses  = direct count of hand-27-class busts avoided")
    print("=" * 72)

    Path("harness/results/tail_analysis_79_vs_710.json").write_text(
        json.dumps({"s9": s9, "s10": s10}, indent=2)
    )
    print(f"\nSaved: harness/results/tail_analysis_79_vs_710.json")


if __name__ == "__main__":
    main()
