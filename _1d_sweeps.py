"""1D sweeps on 4 candidate parameters. For each, test 5 values and report
the heldout pool sum at each — find if there's an interior optimum.

If any param shows clear curvature > baseline SE, that's the candidate for V80c.
If all flat, parametric search is exhausted.
"""
import sys, time
sys.path.insert(0, ".")
from harness.match_runner import compare, aggregate_by_opponent
from harness.opponents.registry import load_pool

SWEEPS = {
    "pot_odds_buffer_normal": [0.08, 0.10, 0.12, 0.14, 0.16],
    "equity_call_threshold":  [0.35, 0.39, 0.43, 0.47, 0.51],
    "bluff_freq_oop":         [0.01, 0.025, 0.04, 0.055, 0.07],
    "cbet_freq_base":         [0.50, 0.55, 0.60, 0.65, 0.70],
}


def run_variant(env, pool):
    res = compare(
        bot_a_path="harness/skantbot7_13_dev/bot.py",
        bot_b_path="harness/skantbot7_13_dev/bot.py",
        opponent_pool=pool,
        n_seeds=30, n_workers=2, n_hands=400,
        show_progress=False, mode="6max", n_tables=10,
        env_overrides=env,
    )
    agg = aggregate_by_opponent(res)
    mean = sum(s.get("a_mean", 0) for s in agg.values())
    se = (sum(s.get("a_stderr", 0)**2 for s in agg.values()))**0.5
    return mean, se


if __name__ == "__main__":
    train = load_pool(include_heldout=False)
    held = load_pool(include_heldout=True)
    heldout_only = {k:v for k,v in held.items() if k not in train}

    print(f"Heldout pool: {len(heldout_only)} opps")
    print(f"Each point: 30 seeds × 10 tables × 400 hands\n")

    all_results = {}
    t_start = time.time()
    for param, values in SWEEPS.items():
        print(f"\n=== {param} ===")
        results = []
        for v in values:
            env = {f"SKANT_{param.upper()}": str(v)}
            t0 = time.time()
            mean, se = run_variant(env, heldout_only)
            dt = time.time() - t0
            print(f"  {param}={v:<6}  mean={mean:+7.0f}  se={se:5.0f}  ({dt:.0f}s)", flush=True)
            results.append((v, mean, se))
        all_results[param] = results
    print(f"\nTotal elapsed: {(time.time()-t_start)/60:.1f} min")

    # Summary: is there curvature?
    print("\n" + "=" * 72)
    print("CURVATURE ANALYSIS — does any param show interior optimum > baseline?")
    print("=" * 72)
    for param, results in all_results.items():
        means = [m for _, m, _ in results]
        ses = [s for _, _, s in results]
        max_idx = means.index(max(means))
        best_val = results[max_idx][0]
        best_mean = means[max_idx]
        # Median SE as noise floor
        median_se = sorted(ses)[len(ses)//2]
        # Range of means vs noise
        mean_range = max(means) - min(means)
        signal_ratio = mean_range / median_se if median_se > 0 else 0
        print(f"  {param:<30} best={best_val:<6} mean={best_mean:+.0f}  range={mean_range:.0f}  median_SE={median_se:.0f}  signal/noise={signal_ratio:.2f}")
        if max_idx in (0, len(means)-1):
            print(f"    → max at edge, not interior optimum")
        elif signal_ratio < 1.0:
            print(f"    → flat curve (signal/noise < 1)")
        else:
            print(f"    → interior optimum at {best_val}, signal/noise = {signal_ratio:.2f}")
