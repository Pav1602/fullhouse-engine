"""Phase 2c confirmation probe: does 7.7 still bluff-raise into min_raiser
(a never-folder) and lose chips doing it?

Reads probe JSONL from SKANT_PROBE_DIR (debug bot vs min_raiser) and measures
how often the bot makes a low-equity postflop RAISE and what those hands cost.
"""
import json
import glob
import sys
from collections import defaultdict

probe_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/probe_2c"

decisions = []          # per-decision records
pnl = {}                # (match_id, hand_id) -> chip_delta
gate_fired = 0

for path in glob.glob(f"{probe_dir}/*.jsonl"):
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = r.get("type")
            if t == "hand_summary":
                pnl[(r["match_id"], r["hand_id"])] = r["chip_delta"]
            elif t == "opp_profiles":
                continue
            elif "action" in r:
                decisions.append(r)
                if r.get("phase2b_gate_fired"):
                    gate_fired += 1

# Group decisions by hand
by_hand = defaultdict(list)
for d in decisions:
    by_hand[(d["match_id"], d["hand_id"])].append(d)

n_hands = len(by_hand)
total_pnl = sum(pnl.values())

BLUFF_EQ = 0.35      # a raise below this equity is not a value raise
NEAR_ZERO = 0.15     # "eq ~ 0" — the canonical 2c river bluff-raise

hands_with_bluff_raise = []      # any postflop low-eq raise
hands_with_river_bluffraise = [] # river, facing a bet, eq < NEAR_ZERO
n_postflop_raises = 0
n_low_eq_raises = 0
n_river_bluffraises = 0

for key, decs in by_hand.items():
    has_bluff = False
    has_river_bluff = False
    for d in decs:
        if d.get("street") == "preflop":
            continue
        if d.get("action") != "raise":
            continue
        n_postflop_raises += 1
        eq = d.get("eq")
        if eq is None:
            continue
        if eq < BLUFF_EQ:
            n_low_eq_raises += 1
            has_bluff = True
        if (d.get("street") == "river" and d.get("facing_bet")
                and eq < NEAR_ZERO):
            n_river_bluffraises += 1
            has_river_bluff = True
    if has_bluff:
        hands_with_bluff_raise.append(key)
    if has_river_bluff:
        hands_with_river_bluffraise.append(key)


def summary(label, keys):
    deltas = [pnl[k] for k in keys if k in pnl]
    if not deltas:
        print(f"  {label}: 0 hands (no P&L join)")
        return 0.0
    tot = sum(deltas)
    mean = tot / len(deltas)
    losers = sum(1 for x in deltas if x < 0)
    print(f"  {label}: {len(deltas)} hands | "
          f"mean P&L {mean:+.1f} | total {tot:+.0f} | "
          f"losers {losers}/{len(deltas)} ({100*losers/len(deltas):.0f}%)")
    return tot


print(f"=== Phase 2c probe — debug bot (=7.7) vs min_raiser ===")
print(f"hands: {n_hands} | total P&L: {total_pnl:+.0f} "
      f"({total_pnl/n_hands:+.1f}/hand)")
print(f"phase2b gate fired: {gate_fired} (expect 0 — confirms 2b inert)")
print(f"postflop raises: {n_postflop_raises} | "
      f"low-eq (<{BLUFF_EQ}) raises: {n_low_eq_raises} | "
      f"river bluff-raises facing bet (eq<{NEAR_ZERO}): {n_river_bluffraises}")
print()
print("P&L by hand category:")
summary("ALL hands", list(by_hand.keys()))
bluff_tot = summary(f"hands w/ a low-eq postflop raise", hands_with_bluff_raise)
river_tot = summary(f"hands w/ a river bluff-raise (the 2c spot)",
                    hands_with_river_bluffraise)
print()
frac = 100 * len(hands_with_river_bluffraise) / max(n_hands, 1)
print(f"2c-spot hands are {frac:.1f}% of all hands; "
      f"aggregate chip impact {river_tot:+.0f} "
      f"({100*river_tot/total_pnl:+.0f}% of total P&L)" if total_pnl else "")
