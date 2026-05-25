"""CRN preservation: compare(skant, skant, pool) must produce
paired_diff_mean == 0.0 exactly for every opponent. Any nondeterminism in
the bot or harness invalidates every sweep result (CLAUDE.md)."""
import sys
sys.path.insert(0, ".")
from harness.match_runner import compare, aggregate_by_opponent
from harness.opponents.registry import load_pool, SKANTBOT_TUNABLE_PATH


def main():
    pool = load_pool(include_heldout=False)
    results = compare(
        bot_a_path=SKANTBOT_TUNABLE_PATH,
        bot_b_path=SKANTBOT_TUNABLE_PATH,
        opponent_pool=pool,
        n_seeds=5, n_workers=12, n_hands=200,
        show_progress=False, mode="6max", n_tables=5,
    )
    agg = aggregate_by_opponent(results)
    nonzero = []
    for opp, stats in agg.items():
        pd = stats.get("paired_diff_mean", None)
        if pd is None or abs(pd) > 1e-9:
            nonzero.append((opp, pd))
    if nonzero:
        print("FAIL — CRN broken. Opponents with paired_diff_mean != 0:")
        for opp, pd in nonzero:
            print(f"  {opp:<20} paired_diff_mean = {pd}")
        sys.exit(1)
    print(f"PASS — paired_diff_mean == 0.0 for all {len(agg)} opponents.")
    print(f"(self-compare on {len(pool)} opponents, n_seeds=5)")


if __name__ == "__main__":
    main()
