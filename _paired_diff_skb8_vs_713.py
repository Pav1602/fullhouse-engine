"""V81 Step 1 — Gates D + E: paired-diff skantbot8 vs 7.13 (and vs 7.9).

For each pool, runs the harness CRN compare:
    a = skantbot8 (new), b = 7.13 (baseline)
and reports per-opp Δ (= a_mean - b_mean). Positive Δ means skantbot8 wins.

Gate D: TRAIN_EXPANDED_V81 — Σ Δ > 0, no single opp <-2σ regression.
Gate E: UNSEEN_VALIDATION_V81 — same standard.

Usage:
    python _paired_diff_skb8_vs_713.py <pool: train_v81|heldout_v81>
                                       [n_seeds=30] [n_tables=20]
"""
import sys, json
sys.path.insert(0, ".")


def main():
    pool_type = sys.argv[1] if len(sys.argv) > 1 else "train_v81"
    n_seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    n_tables = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    baseline_path = sys.argv[4] if len(sys.argv) > 4 else "bots/skantbot7.13/bot.py"
    bot_a_override = sys.argv[5] if len(sys.argv) > 5 else "bots/skantbot8/bot.py"

    from harness.match_runner import compare
    from harness.opponents.registry import (
        TRAIN_EXPANDED_V81, UNSEEN_VALIDATION_V81,
    )

    if pool_type == "train_v81":
        pool = dict(TRAIN_EXPANDED_V81)
    elif pool_type == "heldout_v81":
        pool = dict(UNSEEN_VALIDATION_V81)
    else:
        sys.exit(f"unknown pool: {pool_type}")

    skb8_path = bot_a_override
    a_label = skb8_path.rsplit("/", 2)[-2]
    base_label = baseline_path.rsplit("/", 2)[-2]
    print(f"a = {a_label} ({skb8_path})")
    print(f"b = {base_label} ({baseline_path})")
    print(f"pool = {pool_type} ({len(pool)} opps), n_seeds={n_seeds}, "
          f"n_tables={n_tables}, mode=6max")
    print()

    res = compare(
        bot_a_path=skb8_path,
        bot_b_path=baseline_path,
        opponent_pool=pool,
        n_seeds=n_seeds, n_workers=24, n_hands=200,
        show_progress=False, mode="6max", n_tables=n_tables,
    )
    from harness.match_runner import aggregate_by_opponent
    agg = aggregate_by_opponent(res)

    print(f"{'opp':<22} {a_label[:10]:>10} {'base_mean':>10} {'Δ':>10} "
          f"{'pd_mean':>10} {'pd_se':>8} {'σ':>6}")
    sum_delta = 0.0
    worst = (None, 0.0, 0.0)
    over_2sigma_loss = []
    for opp in sorted(agg):
        s = agg[opp]
        a = s["a_mean"]; b = s["b_mean"]
        pd = s.get("paired_diff_mean", a - b)
        pdse = s.get("paired_diff_stderr", 0.0)
        sigma = pd / pdse if pdse > 0 else 0.0
        delta = a - b
        sum_delta += delta
        if sigma < worst[2] or worst[0] is None:
            worst = (opp, delta, sigma)
        if sigma < -2.0:
            over_2sigma_loss.append((opp, delta, sigma))
        print(f"{opp:<22} {a:>+10.0f} {b:>+10.0f} {delta:>+10.0f} "
              f"{pd:>+10.0f} {pdse:>8.0f} {sigma:>+6.2f}")

    print()
    avg_delta = sum_delta / len(agg) if agg else 0.0
    print(f"avg Δ across opps: {avg_delta:+.0f} chips/opp")
    print(f"sum Δ: {sum_delta:+.0f}")
    if worst[0]:
        print(f"worst opp: {worst[0]} Δ={worst[1]:+.0f} σ={worst[2]:+.2f}")
    if over_2sigma_loss:
        print(f"\n⚠️  >2σ regressions ({len(over_2sigma_loss)}):")
        for opp, d, sig in over_2sigma_loss:
            print(f"    {opp:<22} Δ={d:+.0f} σ={sig:+.2f}")

    out = {
        "pool": pool_type, "n_seeds": n_seeds, "n_tables": n_tables,
        "skb8_path": skb8_path, "baseline_path": baseline_path,
        "avg_delta": avg_delta, "sum_delta": sum_delta,
        "worst_opp": worst[0], "worst_delta": worst[1], "worst_sigma": worst[2],
        "over_2sigma_loss": over_2sigma_loss,
        "per_opp": {k: dict(v) for k, v in agg.items()},
    }
    out_path = f"harness/results/gate_DE_{a_label.replace('.','_')}_vs_{base_label.replace('.','_')}_{pool_type}.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved: {out_path}")

    # --- Gate verdict ---
    # Train pool (train_v81): require avg_delta > 0 AND no >2σ regression.
    # Heldout pool (heldout_v81): require avg_delta > 0 OR no >2σ regression.
    has_2sigma_loss = bool(over_2sigma_loss)
    if pool_type == "train_v81":
        passed = (avg_delta > 0) and (not has_2sigma_loss)
        rule = "avg_delta > 0 AND no >2σ regression"
    elif pool_type == "heldout_v81":
        passed = (avg_delta > 0) or (not has_2sigma_loss)
        rule = "avg_delta > 0 OR no >2σ regression"
    else:
        passed = True
        rule = "no-op"
    print(f"\nGate verdict ({pool_type}): rule = {rule}")
    if passed:
        print(f"✓ PASS  (avg_delta={avg_delta:+.0f}, "
              f"n_regressions={len(over_2sigma_loss)})")
    else:
        print(f"✗ FAIL  (avg_delta={avg_delta:+.0f}, "
              f"n_regressions={len(over_2sigma_loss)})")
        sys.exit(1)


if __name__ == "__main__":
    main()
