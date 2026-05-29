"""Paired-diff CRN: 7.14 vs 7.13 on TRAIN pool + HELDOUT pool.
Convention: paired_Δ = 7.13 − 7.14. NEGATIVE means 7.14 gained."""
import sys
sys.path.insert(0, ".")
from harness.match_runner import compare, aggregate_by_opponent
from harness.opponents.registry import load_pool

B13 = "bots/skantbot7.13/bot.py"
B14 = "bots/skantbot7.14/bot.py"

def run(pool, label):
    print(f"\n=== {label} (pool size {len(pool)}) ===")
    res = compare(
        bot_a_path=B13, bot_b_path=B14,
        opponent_pool=pool,
        n_seeds=30, n_workers=2, n_hands=400,
        show_progress=False, mode="6max", n_tables=10,
    )
    agg = aggregate_by_opponent(res)
    total_pd = 0; total_se_sq = 0; wins_14 = 0; wins_13 = 0
    sig_gain = []; sig_loss = []
    print(f"{'opp':<22} {'7.13_mean':>10} {'7.14_mean':>10} {'paired_Δ':>10} {'σ':>6}")
    print("-" * 75)
    for opp, s in sorted(agg.items()):
        pd = s.get("paired_diff_mean", 0) or 0
        se = s.get("paired_diff_stderr", 0) or 0
        am = s.get("a_mean", 0) or 0
        bm = s.get("b_mean", 0) or 0
        sig = (pd / se) if se > 0 else 0
        total_pd += pd; total_se_sq += se ** 2
        if pd < 0: wins_14 += 1
        else: wins_13 += 1
        if pd < 0 and sig < -1.5: sig_gain.append((opp, pd, sig))
        if pd > 0 and sig > +2.0: sig_loss.append((opp, pd, sig))
        print(f"{opp:<22} {am:>10.0f} {bm:>10.0f} {pd:>+10.0f} {sig:>+6.1f}")
    pool_se = total_se_sq ** 0.5
    print("-" * 75)
    print(f"{'TOTAL':<22} {'':>10} {'':>10} {total_pd:>+10.0f}  σ={total_pd/pool_se if pool_se>0 else 0:+.2f}")
    print(f"7.14 wins: {wins_14}/{len(agg)}   7.13 wins: {wins_13}/{len(agg)}")
    if sig_gain:
        print(f"\nSig gains for 7.14 (σ < -1.5):")
        for o, p, s in sig_gain: print(f"  {o}: Δ={p:+.0f} σ={s:+.1f}")
    if sig_loss:
        print(f"\nSig REGRESSIONS — 7.14 loses (σ > +2.0):")
        for o, p, s in sig_loss: print(f"  {o}: Δ={p:+.0f} σ={s:+.1f}")
    return total_pd, pool_se, sig_loss

if __name__ == "__main__":
    train = load_pool(include_heldout=False)
    held = load_pool(include_heldout=True)
    heldout_only = {k: v for k, v in held.items() if k not in train}

    print(f"Train opps: {len(train)}, Heldout opps: {len(heldout_only)}")
    tot_train, se_train, sig_train = run(train, "TRAIN")
    tot_held, se_held, sig_held = run(heldout_only, "HELDOUT")

    print("\n" + "=" * 75)
    print("VERDICT")
    print("=" * 75)
    train_ok = tot_train < 0
    held_ok = not sig_held
    print(f"Train net positive for 7.14: {'PASS' if train_ok else 'FAIL'} (Δ={tot_train:+.0f})")
    print(f"Heldout no >2σ regression:    {'PASS' if held_ok else 'FAIL'}")
