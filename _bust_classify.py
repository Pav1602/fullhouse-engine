"""Deeper analysis of bust hands from _bust_analyze.py JSON output.

For each bust:
  - Identify skant's role (preflop aggressor / caller / blind defender)
  - Determine the street where most chips went in
  - Classify as cooler (correct play, bad outcome) vs leak (-EV decision)
  - Group by family

Heuristics for cooler vs leak:
  - Skant strong hand (Two Pair+) vs opponent stronger (Set+, Boat+) = COOLER
  - Skant weak hand (Pair or worse) called large bet / shove = LEAK
  - Skant folded after large investment on flop/turn = MODE-A leak (cbet/barrel)
"""
import json, sys
from collections import Counter, defaultdict


STRENGTH_RANK = {
    "High Card": 0, "Pair": 1, "Two Pair": 2, "Trips": 3, "Three of": 3,
    "Straight": 4, "Flush": 5, "Full House": 6, "Quads": 7, "Straight Flush": 8,
}


def strength_score(s):
    if not s or s == "?": return -1
    for k, v in STRENGTH_RANK.items():
        if k in s:
            return v
    return -1


def family(bust):
    """Single-label family classification."""
    tags = bust.get("tags", "")
    street = bust.get("final_street", "?")
    skant_str = strength_score(bust.get("skant_strength", "?"))
    showdown = bust.get("showdown_opps", [])
    revealed = bust.get("skant_revealed")

    # Skant folded (didn't reach showdown) but still lost a lot
    if not revealed:
        if street == "preflop":
            return "preflop_fold_after_invest"
        return f"{street}_fold_after_invest"  # MODE A: cbet/barrel disaster

    # Skant reached showdown
    if not showdown:
        # We have skant's cards but no opp cards — opp folded? Wait that'd mean SKANT won.
        # But this is a bust hand (loss>0). Edge case — probably side pot.
        return "showdown_no_opp_visible"

    best_opp_str = max(strength_score(s) for _, _, s in showdown)
    delta_strength = best_opp_str - skant_str

    if delta_strength <= 0 and skant_str >= 2:
        # Skant tied or had stronger but still lost the pot — multiway, side pot, etc.
        return "showdown_skant_lost_with_strong_hand"
    if delta_strength >= 2:
        if "flush_board" in tags and "opp_made_flush" in tags:
            return "cooler_skant_pair_or_2pair_vs_flush"
        if "paired_board" in tags and "opp_set" in tags:
            return "cooler_skant_strong_vs_opp_set"
        if "opp_made_straight" in tags:
            return "cooler_skant_strong_vs_opp_straight"
        if "opp_boat_or_quads" in tags:
            return "cooler_skant_2pair_vs_boat"
        return "cooler_skant_strong_vs_opp_stronger"
    if skant_str <= 1:
        # Pair or High Card vs better — possible leak
        if street in ("turn", "river"):
            return "leak_called_with_weak_hand_late_street"
        return "leak_called_with_weak_hand"
    return f"mixed_{street}_str{skant_str}vs{best_opp_str}"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "harness/results/bust_survey_710.json"
    d = json.load(open(path))
    busts = d["busts"]
    print(f"Loaded {len(busts)} busts from {path}")
    print(f"Total chips lost: {d['total_loss']:,}   Across {d['n_matches']} matches × {d['n_hands_per']} hands\n")

    fams = Counter()
    fam_loss = defaultdict(int)
    fam_examples = defaultdict(list)
    for b in busts:
        f = family(b)
        fams[f] += 1
        fam_loss[f] += b["loss"]
        fam_examples[f].append(b)

    print("=" * 80)
    print(f"{'family':<48} {'n':>5} {'total_loss':>13} {'avg':>8} {'mean$/hand':>11}")
    print("-" * 80)
    total_loss = d["total_loss"]
    for f, n in sorted(fams.items(), key=lambda x: -fam_loss[x[0]]):
        avg = fam_loss[f] // n
        pct = fam_loss[f] / total_loss * 100
        per_hand = fam_loss[f] / d["total_hands"]
        print(f"  {f:<46} {n:>5} {fam_loss[f]:>+13,} {avg:>8} {per_hand:>10.1f}")
    print("-" * 80)
    print(f"  {'TOTAL':<46} {len(busts):>5} {total_loss:>+13,}")

    # Show 3 worst examples from each top family
    print()
    print("=" * 80)
    print("WORST 3 EXAMPLES FROM EACH FAMILY")
    print("-" * 80)
    for f, n in sorted(fams.items(), key=lambda x: -fam_loss[x[0]])[:6]:
        examples = sorted(fam_examples[f], key=lambda b: -b["loss"])[:3]
        print(f"\n  {f} (n={n}, total ${fam_loss[f]:,})")
        for b in examples:
            opp = " ; ".join(f"{bid}:{cards}={s}" for bid, cards, s in b.get("showdown_opps", [])[:2])
            print(f"    {b['hand_id']:<32} loss={b['loss']:>6}  board={str(b['board']):<28} "
                  f"skant={b.get('skant_revealed')}={b['skant_strength']}")
            if opp:
                print(f"      vs {opp}")
            # Show the action log compactly
            log = b.get("action_log", [])
            log_compact = []
            for e in log:
                a, amt = e.get("action", ""), e.get("amount", 0)
                if a in ("raise", "all_in"):
                    log_compact.append(f"s{e.get('seat')}{a[0]}{amt}")
                elif a in ("call",):
                    log_compact.append(f"s{e.get('seat')}c{amt}")
                elif a in ("check",):
                    log_compact.append(f"s{e.get('seat')}k")
                elif a == "fold":
                    log_compact.append(f"s{e.get('seat')}F")
            print(f"      log: {' '.join(log_compact)}")


if __name__ == "__main__":
    main()
