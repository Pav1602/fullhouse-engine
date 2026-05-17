"""
Baseline analysis against the heldout pool, with overfitting detection.
"""

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from harness.match_runner import compare
from harness.opponents.registry import (
    load_pool, validate_pool, SKANTBOT_TUNABLE_PATH, _HELDOUT
)

def run_heldout_validation(
    mode: str = "6max",
    n_tables: int = 10,n_seeds: int = 100, n_workers: int = 8, n_hands: int = 200):
    print("=== Training Pool Evaluation ===")
    training_pool = load_pool(include_heldout=False)
    validate_pool(training_pool)
    
    training_results = compare(
        bot_a_path=SKANTBOT_TUNABLE_PATH,
        bot_b_path=SKANTBOT_TUNABLE_PATH,
        opponent_pool=training_pool,
        n_seeds=n_seeds,
        n_workers=n_workers,
        n_hands=n_hands,
        show_progress=True,
        mode=mode,
        n_tables=n_tables,
    )
    
    print("\n=== Heldout Pool Evaluation ===")
    full_pool = load_pool(include_heldout=True)
    heldout_pool = {k: v for k, v in full_pool.items() if k in _HELDOUT}
    validate_pool(heldout_pool)
    
    heldout_results = compare(
        bot_a_path=SKANTBOT_TUNABLE_PATH,
        bot_b_path=SKANTBOT_TUNABLE_PATH,
        opponent_pool=heldout_pool,
        n_seeds=n_seeds,
        n_workers=n_workers,
        n_hands=n_hands,
        show_progress=True,
        mode=mode,
        n_tables=n_tables,
    )
    
    train_means = [s["a_mean"] for s in training_results.values()]
    train_mean = sum(train_means) / len(train_means) if train_means else 0
    
    heldout_means = [s["a_mean"] for s in heldout_results.values()]
    heldout_mean = sum(heldout_means) / len(heldout_means) if heldout_means else 0
    
    gap = (train_mean - heldout_mean) / train_mean if train_mean != 0 else 0
    
    print(f"\n=== Validation Summary ===")
    print(f"Training Mean: {train_mean:+.1f}")
    print(f"Heldout Mean:  {heldout_mean:+.1f}")
    print(f"Gap:           {gap:.1%}")
    
    if gap > 0.30:
        print(f"\nWARNING: held-out delta is {gap:.1%} below training. Likely overfitting.")
    else:
        print(f"\nSUCCESS: held-out delta is within acceptable bounds (< 30%).")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Heldout validation for skantbot")
    p.add_argument("--seeds",   type=int, default=100)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--hands",   type=int, default=200)
    p.add_argument("--mode", default="6max", choices=["hu", "6max"])
    p.add_argument("--n-tables", type=int, default=10)
    args = p.parse_args()
    
    run_heldout_validation(n_seeds=args.seeds, n_workers=args.workers, n_hands=args.hands, mode=args.mode, n_tables=args.n_tables)
