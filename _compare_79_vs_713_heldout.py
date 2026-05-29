"""Verify 7.13 doesn't overfit train pool — paired-diff vs 7.9 on HELDOUT."""
import sys
sys.path.insert(0, ".")
from harness.match_runner import compare, aggregate_by_opponent
from harness.opponents.registry import load_pool


if __name__ == "__main__":
    train = load_pool(include_heldout=False)
    held = load_pool(include_heldout=True)
    heldout_only = {k: v for k, v in held.items() if k not in train}

    print(f"7.9 vs 7.13 on HELDOUT ({len(heldout_only)} opps)")
    res = compare(
        bot_a_path="bots/skantbot7.9/bot.py", bot_b_path="bots/skantbot7.13/bot.py",
        opponent_pool=heldout_only,
        n_seeds=30, n_workers=2, n_hands=400,
        show_progress=False, mode="6max", n_tables=10,
    )
    agg = aggregate_by_opponent(res)
    tot = 0; sq = 0; wins13 = 0; loses13 = 0; sig_loss = []
    print(f"\n{'opp':<20} {'7.9_m':>8} {'7.13_m':>8} {'Δ':>8} {'σ':>6}")
    print("-" * 60)
    for opp, s in sorted(agg.items()):
        pd = s.get("paired_diff_mean", 0) or 0
        se = s.get("paired_diff_stderr", 0) or 0
        am = s.get("a_mean", 0); bm = s.get("b_mean", 0)
        sig = pd/se if se>0 else 0
        tot += pd; sq += se**2
        if pd < 0: wins13 += 1
        else: loses13 += 1
        if pd > 0 and sig > 2.0: sig_loss.append((opp, pd, sig))
        print(f"{opp:<20} {am:>8.0f} {bm:>8.0f} {pd:>+8.0f} {sig:>+6.1f}")
    pool_se = sq**0.5
    print("-" * 60)
    print(f"{'TOTAL':<20} {'':>8} {'':>8} {tot:>+8.0f}  σ={tot/pool_se if pool_se>0 else 0:+.2f}")
    print(f"\n7.13 wins {wins13}/{len(agg)}, loses {loses13}/{len(agg)}")
    if sig_loss:
        print(f"Regressions (>2σ): {len(sig_loss)}")
        for o,p,s in sig_loss: print(f"  {o}: Δ={p:+.0f} σ={s:+.1f}")
    else:
        print("✓ NO heldout regressions > 2σ")
