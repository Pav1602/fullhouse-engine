"""
Baseline analysis: skantbot4 (default config) vs the full training pool.

Usage:
    python3 harness/baseline.py [options]
    python3 -m harness.baseline  [options]

Options:
    --seeds N    Seeds per opponent (default: 100)
    --workers N  Parallel workers (default: 8)
    --hands N    Hands per match (default: 200)
    --no-save    Skip writing the results JSON

Output:
    Sorted per-opponent table printed to stdout.
    JSON saved to harness/results/baseline_<timestamp>.json

The baseline uses compare(skant, skant, pool) so a_mean gives skantbot4's
absolute chip delta position-balanced — paired_diff is always ~0 when A≡B.
"""

import sys
import json
import datetime
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from harness.match_runner import compare
from harness.opponents.registry import (
    load_pool, validate_pool, SKANTBOT_TUNABLE_PATH
)

_RESULTS_DIR = Path(__file__).parent / "results"


def run_baseline(
    n_seeds:   int  = 100,
    n_workers: int  = 8,
    n_hands:   int  = 200,
    save:      bool = True,
    pool:      dict = None,
    pool_name: str  = "training pool"
) -> dict:
    """
    Run skantbot4 (default config) against the specified pool.

    Returns the compare() output dict.
    Prints a per-opponent breakdown sorted by chip delta (best first).
    Saves to harness/results/baseline_<timestamp>.json when save=True.
    """
    if pool is None:
        pool = load_pool(include_heldout=False)
    
    validate_pool(pool)

    total_matches = len(pool) * n_seeds * 4
    print(f"=== Baseline: skantbot4 (default config) ===")
    print(f"Pool      : {pool_name}")
    print(f"Opponents : {', '.join(pool.keys())}")
    print(f"Seeds     : {n_seeds}  |  Hands/match: {n_hands}  |  Workers: {n_workers}")
    print(f"Total matches: {total_matches}\n")

    # compare(A, A, pool) → a_mean is skantbot4's absolute chip delta
    results = compare(
        bot_a_path=SKANTBOT_TUNABLE_PATH,
        bot_b_path=SKANTBOT_TUNABLE_PATH,
        opponent_pool=pool,
        n_seeds=n_seeds,
        n_workers=n_workers,
        n_hands=n_hands,
        show_progress=True,
    )

    # Print sorted table (best opponents first)
    col = 25
    print(f"\n{'Opponent':<{col}} {'Mean Δ':>10} {'StdErr':>10} {'n':>6}")
    print("-" * (col + 30))
    sorted_items = sorted(results.items(), key=lambda x: -x[1]["a_mean"])
    for opp_id, stats in sorted_items:
        note = "  <- bleeding" if stats["a_mean"] < -100 else ""
        print(f"{opp_id:<{col}} {stats['a_mean']:>+10.1f} "
              f"{stats['a_stderr']:>10.1f} {stats['n']:>6}{note}")
    print()

    if save:
        _RESULTS_DIR.mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = _RESULTS_DIR / f"baseline_{ts}.json"
        payload = {
            "timestamp":  ts,
            "n_seeds":    n_seeds,
            "n_hands":    n_hands,
            "bot_path":   SKANTBOT_TUNABLE_PATH,
            "results":    results,
        }
        out_path.write_text(json.dumps(payload, indent=2))
        print(f"Saved: {out_path}")

    return results


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Baseline: skantbot4 vs training pool")
    p.add_argument("--seeds",   type=int, default=100)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--hands",   type=int, default=200)
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--heldout", action="store_true", help="Run against the heldout pool only")
    args = p.parse_args()

    if args.heldout:
        pool = load_pool(include_heldout=True)
        # Filter to only the heldout bots
        from harness.opponents.registry import _HELDOUT
        pool = {k: v for k, v in pool.items() if k in _HELDOUT}
        pool_name = "heldout pool"
    else:
        pool = load_pool(include_heldout=False)
        pool_name = "training pool"

    run_baseline(n_seeds=args.seeds, n_workers=args.workers,
                 n_hands=args.hands, save=not args.no_save,
                 pool=pool, pool_name=pool_name)
