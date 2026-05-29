"""Full 7.14 verification: gates 2-6 in one go.
2. min_raiser HU (preserve)
3. paired-diff 7.14 vs 7.13 (train)
4. paired-diff 7.14 vs 7.13 (heldout) — the key gate
5. paired-diff 7.14 vs 7.9 (train)
6. paired-diff 7.14 vs 7.9 (heldout) — the new bar
"""
import sys
sys.path.insert(0, ".")
from harness.match_runner import compare, aggregate_by_opponent
from harness.opponents.registry import load_pool


def paired_diff(label, a_path, b_path, pool):
    res = compare(
        bot_a_path=a_path, bot_b_path=b_path,
        opponent_pool=pool,
        n_seeds=30, n_workers=2, n_hands=400,
        show_progress=False, mode="6max", n_tables=10,
    )
    agg = aggregate_by_opponent(res)
    tot = 0; sq = 0; wins_b = 0; loses_b = 0; sig_b_loses = []
    for opp, s in sorted(agg.items()):
        pd = s.get("paired_diff_mean", 0) or 0
        se = s.get("paired_diff_stderr", 0) or 0
        sig = pd/se if se>0 else 0
        tot += pd; sq += se**2
        if pd < 0: wins_b += 1
        else: loses_b += 1
        if pd > 0 and sig > 2.0: sig_b_loses.append((opp, pd, sig))
    pool_se = sq**0.5
    overall_sigma = tot/pool_se if pool_se>0 else 0
    print(f"  {label}: {b_path.split('/')[-2]} vs {a_path.split('/')[-2]}: Δ={tot:+.0f}  σ={overall_sigma:+.2f}  B_wins {wins_b}/{len(agg)}  sig_B_losses={len(sig_b_loses)}")
    if sig_b_loses:
        for o,p,s in sig_b_loses: print(f"    REGRESSION: {o}: Δ={p:+.0f} σ={s:+.1f}")
    return tot, overall_sigma, sig_b_loses


if __name__ == "__main__":
    train = load_pool(include_heldout=False)
    held = load_pool(include_heldout=True)
    heldout_only = {k:v for k,v in held.items() if k not in train}

    print(f"=== Gate 2: min_raiser HU preservation ===")
    res = compare(
        bot_a_path="bots/skantbot7.14/bot.py", bot_b_path="bots/skantbot7.14/bot.py",
        opponent_pool={"min_raiser": "harness/opponents/archetypes/min_raiser/bot.py"},
        n_seeds=100, n_workers=2, n_hands=400, show_progress=False, mode="hu",
    )
    mr = res["min_raiser"]
    print(f"  7.14 vs min_raiser HU: {mr['a_mean']:+.0f} ± {mr['a_stderr']:.0f}  ({'PASS' if mr['a_mean']>=3000 else 'FAIL'})")

    print(f"\n=== Gates 3-6: paired-diffs ===")
    print("Convention: 'B vs A' shows B's perf relative to A. NEGATIVE Δ means B (the 7.14) gained.")
    t3, s3, _ = paired_diff("Gate 3", "bots/skantbot7.13/bot.py", "bots/skantbot7.14/bot.py", train)
    t4, s4, sig4 = paired_diff("Gate 4", "bots/skantbot7.13/bot.py", "bots/skantbot7.14/bot.py", heldout_only)
    t5, s5, _ = paired_diff("Gate 5", "bots/skantbot7.9/bot.py", "bots/skantbot7.14/bot.py", train)
    t6, s6, sig6 = paired_diff("Gate 6", "bots/skantbot7.9/bot.py", "bots/skantbot7.14/bot.py", heldout_only)

    print("\n=== SUMMARY ===")
    print(f"Gate 2 min_raiser HU:       {mr['a_mean']:+.0f}  ({'PASS' if mr['a_mean']>=3000 else 'FAIL'})")
    print(f"Gate 3 7.14 vs 7.13 train:  Δ={t3:+.0f}  ({'PASS' if t3 <= 200 else 'WARN' if t3 < 500 else 'FAIL'})")
    print(f"Gate 4 7.14 vs 7.13 heldout:Δ={t4:+.0f}  ({'IMPROVED' if t4 < -100 else 'NEUTRAL' if t4 < 100 else 'WORSE'})")
    print(f"Gate 5 7.14 vs 7.9 train:   Δ={t5:+.0f}  ({'PASS' if t5 <= 200 else 'WARN' if t5 < 500 else 'FAIL'})")
    print(f"Gate 6 7.14 vs 7.9 heldout: Δ={t6:+.0f}  ({'BEATS 7.9' if t6 < 0 else 'GAP_CLOSED' if t6 < 3000 else 'GAP_OPEN'})")
    print(f"\nReference: 7.13 vs 7.9 heldout was +6935 (7.13 lost by 175/opp).")
    print(f"If Gate 6 < +3000, we've meaningfully closed the heldout gap.")
