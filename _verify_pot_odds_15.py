"""Verify pot_odds_buffer_normal = 0.15 as a single change vs 7.13 baseline.

Test: 40 seeds × both train and heldout pools, paired-diff CRN.
Goal: confirm signal, check it doesn't hurt train.
"""
import sys
sys.path.insert(0, ".")
from harness.match_runner import compare, aggregate_by_opponent
from harness.opponents.registry import load_pool

ENV = {"SKANT_POT_ODDS_BUFFER_NORMAL": "0.15"}

if __name__ == "__main__":
    train = load_pool(include_heldout=False)
    held = load_pool(include_heldout=True)
    heldout_only = {k:v for k,v in held.items() if k not in train}

    for pool_name, pool in [("TRAIN", train), ("HELDOUT", heldout_only)]:
        # Baseline
        res_b = compare(
            bot_a_path="harness/skantbot7_13_dev/bot.py",
            bot_b_path="harness/skantbot7_13_dev/bot.py",
            opponent_pool=pool,
            n_seeds=40, n_workers=2, n_hands=400,
            show_progress=False, mode="6max", n_tables=10,
            env_overrides=None,
        )
        agg_b = aggregate_by_opponent(res_b)
        mean_b = sum(s.get("a_mean", 0) for s in agg_b.values())
        se_b = (sum(s.get("a_stderr", 0)**2 for s in agg_b.values()))**0.5

        # Override
        res_o = compare(
            bot_a_path="harness/skantbot7_13_dev/bot.py",
            bot_b_path="harness/skantbot7_13_dev/bot.py",
            opponent_pool=pool,
            n_seeds=40, n_workers=2, n_hands=400,
            show_progress=False, mode="6max", n_tables=10,
            env_overrides=ENV,
        )
        agg_o = aggregate_by_opponent(res_o)
        mean_o = sum(s.get("a_mean", 0) for s in agg_o.values())
        se_o = (sum(s.get("a_stderr", 0)**2 for s in agg_o.values()))**0.5

        delta = mean_o - mean_b
        pooled_se = (se_b**2 + se_o**2)**0.5
        sigma = delta / pooled_se if pooled_se > 0 else 0
        print(f"\n{pool_name} pool: ({len(pool)} opps)")
        print(f"  baseline mean: {mean_b:+.0f} ± {se_b:.0f}")
        print(f"  override mean: {mean_o:+.0f} ± {se_o:.0f}")
        print(f"  Δ = {delta:+.0f} ± {pooled_se:.0f}  σ={sigma:+.2f}")

    print(f"\nIf both pools positive → bake into 7.14_v1 as a single-param change.")
