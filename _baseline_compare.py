"""Matched-n baselines: 7.9 (pre-fix) and 7.10 (post-fix) at n_seeds=100
against the same training pool, so per-opponent deltas have matched stderrs."""
import sys, json
from pathlib import Path
sys.path.insert(0, ".")
from harness.match_runner import compare, aggregate_by_opponent
from harness.opponents.registry import load_pool


def run(bot_path, label):
    pool = load_pool(include_heldout=False)
    print(f"\n=== {label} baseline (n_seeds=100) ===  bot: {bot_path}")
    results = compare(
        bot_a_path=bot_path, bot_b_path=bot_path,
        opponent_pool=pool,
        n_seeds=100, n_workers=24, n_hands=200,
        show_progress=False, mode="6max", n_tables=10,
    )
    return aggregate_by_opponent(results)


def main():
    agg_09 = run("bots/skantbot7.9/bot.py", "7.9 (pre-fix baseline)")
    agg_10 = run("bots/skantbot7.10/bot.py", "7.10 (post-fix)")

    print()
    print("=" * 80)
    print(f"{'Opponent':<22} {'7.9 mean':>10} {'7.10 mean':>11} {'Δ':>10} {'σ_pooled':>10}")
    print("-" * 80)
    rows = []
    for opp in sorted(set(agg_09) | set(agg_10)):
        a = agg_09.get(opp, {}); b = agg_10.get(opp, {})
        if "a_mean" not in a or "a_mean" not in b: continue
        d = b["a_mean"] - a["a_mean"]
        s = (a.get("a_stderr", 0) ** 2 + b.get("a_stderr", 0) ** 2) ** 0.5
        rows.append((opp, a["a_mean"], b["a_mean"], d, s))
    rows.sort(key=lambda r: r[3])  # most-negative first
    for opp, m9, m10, d, s in rows:
        sig = "    " if abs(d) < s else (" ⚠ " if abs(d) < 2*s else " !! ")
        print(f"{opp:<22} {m9:>+10.0f} {m10:>+11.0f} {d:>+10.0f} {s:>10.0f}{sig}")
    print("-" * 80)
    print("Annotation: blank = within 1σ (noise); ⚠ = 1-2σ (possible); !! = >2σ (likely real)")

    # Aggregate stats
    total_9 = sum(r[1] for r in rows)
    total_10 = sum(r[2] for r in rows)
    print()
    print(f"Sum of per-opp means:  7.9 = {total_9:+.0f}   7.10 = {total_10:+.0f}   Δ = {total_10 - total_9:+.0f}")

    # Save
    out = {
        "n_seeds": 100, "mode": "6max", "n_hands": 200,
        "agg_09": agg_09, "agg_10": agg_10,
        "rows": [{"opp": r[0], "m9": r[1], "m10": r[2], "delta": r[3], "stderr_pooled": r[4]} for r in rows],
    }
    Path("harness/results/baseline_compare_79_vs_710.json").write_text(json.dumps(out, indent=2))
    print(f"\nSaved: harness/results/baseline_compare_79_vs_710.json")


if __name__ == "__main__":
    main()
