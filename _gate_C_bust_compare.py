"""V81 Gate C — compare two bust surveys (baseline vs new) on the same pool.

Reads two bust-survey JSONs and prints aggregate + per-final-street totals.
Gate C criterion: skantbot8's hero-call late-street class (proxy: river busts)
must NOT grow by >5% vs 7.13 on the same pool.

Usage:
    python _gate_C_bust_compare.py <baseline_json> <new_json>
"""
import sys, json
from collections import Counter, defaultdict

BASE = sys.argv[1] if len(sys.argv) > 1 else \
    "harness/results/bust_survey_skantbot7.13_heldout_v81_n100.json"
NEW = sys.argv[2] if len(sys.argv) > 2 else \
    "harness/results/bust_survey_skantbot8_step1_heldout_v81_n100.json"


def load(path):
    return json.load(open(path))


def by_street(busts):
    c = Counter()
    l = defaultdict(int)
    for x in busts:
        s = x.get("final_street", "?")
        c[s] += 1
        l[s] += x.get("loss", 0)
    return c, l


def by_skant_role(busts):
    # Coarse: did skant reach showdown (likely hero-call) vs fold?
    sd = 0; nsd = 0
    sd_loss = 0; nsd_loss = 0
    for x in busts:
        showdown = bool(x.get("showdown_opps"))
        if showdown:
            sd += 1; sd_loss += x.get("loss", 0)
        else:
            nsd += 1; nsd_loss += x.get("loss", 0)
    return {"showdown": (sd, sd_loss), "fold_or_uncontested": (nsd, nsd_loss)}


def main():
    b = load(BASE)
    n = load(NEW)
    print(f"BASE: {BASE}")
    print(f"  {b['n_busts']} busts, ${b['total_loss']:,} loss, "
          f"{b['total_hands']} hands")
    print(f"NEW:  {NEW}")
    print(f"  {n['n_busts']} busts, ${n['total_loss']:,} loss, "
          f"{n['total_hands']} hands")

    db = n['n_busts'] - b['n_busts']
    dl = n['total_loss'] - b['total_loss']
    print(f"\nΔ (NEW - BASE):  busts={db:+}  loss=${dl:+,}")
    if b['n_busts'] > 0:
        print(f"   pct busts: {db/b['n_busts']*100:+.1f}%")
        print(f"   pct loss:  {dl/b['total_loss']*100:+.1f}%")

    print("\n=== By final_street ===")
    bc, bl = by_street(b['busts'])
    nc, nl = by_street(n['busts'])
    streets = sorted(set(bc) | set(nc))
    print(f"{'street':<10} {'BASE_n':>6} {'NEW_n':>6} {'Δn':>5}  "
          f"{'BASE_$':>10} {'NEW_$':>10} {'Δ$':>10}")
    for s in streets:
        bn, nn = bc[s], nc[s]
        bls, nls = bl[s], nl[s]
        print(f"{s:<10} {bn:>6} {nn:>6} {nn-bn:>+5}  "
              f"${bls:>9,} ${nls:>9,} ${nls-bls:>+9,}")

    print("\n=== By showdown role ===")
    b_role = by_skant_role(b['busts'])
    n_role = by_skant_role(n['busts'])
    for role in ("showdown", "fold_or_uncontested"):
        bn, bls = b_role[role]
        nn, nls = n_role[role]
        print(f"{role:<25} BASE: {bn:>4} (${bls:>10,})  "
              f"NEW: {nn:>4} (${nls:>10,})  Δ: {nn-bn:+} ({nls-bls:+,})")

    # Gate C criterion: showdown bust class (proxy for hero-call) must NOT
    # grow by >5%.
    base_sd = b_role["showdown"][0]
    new_sd = n_role["showdown"][0]
    print(f"\n=== Gate C check (hero-call proxy: showdown busts) ===")
    if base_sd == 0:
        print("(no baseline showdown busts; skipping ratio test)")
    else:
        growth_pct = (new_sd - base_sd) / base_sd * 100
        print(f"Showdown bust growth: {growth_pct:+.1f}% "
              f"(BASE={base_sd}, NEW={new_sd})")
        if growth_pct > 5.0:
            print("✗ GATE C FAIL: showdown bust class grew > 5%")
            sys.exit(1)
        print("✓ GATE C PASS")


if __name__ == "__main__":
    main()
