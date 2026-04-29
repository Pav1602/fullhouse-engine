"""
Fullhouse Harness CLI

Usage:
    python3 -m harness.cli compare <bot_a> <bot_b> [options]

Options:
    --seeds N       Seeds per opponent (default: 100)
    --workers N     Parallel workers (default: 8)
    --hands N       Hands per match (default: 200)
    --opponents F   JSON file {bot_id: bot_path} (default: training pool)
    --output F      Save results JSON to this path

Examples:
    # Compare skantbot3 vs skantbot2 against training pool
    python3 -m harness.cli compare \\
        harness/skantbot_tunable/bot.py \\
        bots/skantbot2/bot.py \\
        --seeds 50 --workers 8

    # A-vs-A acceptance test (paired_diff_mean must be 0.0)
    python3 -m harness.cli compare \\
        bots/aggressor/bot.py bots/aggressor/bot.py \\
        --seeds 5 --workers 2 --hands 50
"""

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def cmd_compare(args: argparse.Namespace) -> None:
    from harness.match_runner import compare
    from harness.opponents.registry import load_pool, validate_pool

    if args.opponents:
        pool = json.loads(Path(args.opponents).read_text())
    else:
        pool = load_pool(include_heldout=False)

    validate_pool(pool)

    print(f"Comparing bots against {len(pool)} opponents, "
          f"{args.seeds} seeds, {args.workers} workers, {args.hands} hands/match")
    print(f"  bot_a: {args.bot_a}")
    print(f"  bot_b: {args.bot_b}\n")

    results = compare(
        bot_a_path=args.bot_a,
        bot_b_path=args.bot_b,
        opponent_pool=pool,
        n_seeds=args.seeds,
        n_workers=args.workers,
        n_hands=args.hands,
    )

    # --- formatted table ---
    COL_W = 25
    print(f"\n{'Opponent':<{COL_W}} {'A_mean':>9} {'±':>2} {'A_se':>7} "
          f"{'B_mean':>9} {'±':>2} {'B_se':>7} "
          f"{'Diff':>9} {'±':>2} {'Diff_se':>7} {'n':>5}")
    print("-" * (COL_W + 9 + 2 + 7 + 9 + 2 + 7 + 9 + 2 + 7 + 5 + 12))

    for opp_id, s in sorted(results.items()):
        print(
            f"{opp_id:<{COL_W}} "
            f"{s['a_mean']:>+9.1f} {'±':>2} {s['a_stderr']:>7.1f} "
            f"{s['b_mean']:>+9.1f} {'±':>2} {s['b_stderr']:>7.1f} "
            f"{s['paired_diff_mean']:>+9.1f} {'±':>2} {s['paired_diff_stderr']:>7.1f} "
            f"{s['n']:>5}"
        )
    print()

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"Results saved to {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python3 -m harness.cli",
        description="Fullhouse bot evaluation harness",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("compare", help="Compare two bots against an opponent pool")
    p.add_argument("bot_a", help="Path to bot_a's bot.py")
    p.add_argument("bot_b", help="Path to bot_b's bot.py")
    p.add_argument("--opponents", default=None,
                   help="JSON file {bot_id: path}. Default: full training pool.")
    p.add_argument("--seeds",   type=int, default=100)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--hands",   type=int, default=200)
    p.add_argument("--output",  default=None)

    args = parser.parse_args()
    if args.command == "compare":
        cmd_compare(args)


if __name__ == "__main__":
    main()
