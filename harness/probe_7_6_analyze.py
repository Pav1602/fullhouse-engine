"""skantbot7.7 Stage 1 — analyse probe JSONL from instrumented 7.6.

Reads harness/results/probe_7_6/*.jsonl and prints the diagnosis table:
action distribution sliced by scenario, postflop role, and cold-start bucket.
"""
import json
import glob
from collections import Counter, defaultdict

recs = []
for fn in glob.glob("harness/results/probe_7_6/*.jsonl"):
    with open(fn) as fh:
        for line in fh:
            line = line.strip()
            if line:
                recs.append(json.loads(line))

print(f"Total decision records: {len(recs)}")
pf = [r for r in recs if r["street"] == "preflop"]
post = [r for r in recs if r["street"] != "preflop"]
print(f"  preflop: {len(pf)}   postflop: {len(post)}")


def pct_table(rows, keyfn, title, actions=("fold", "check", "call", "raise", "all_in")):
    print(f"\n=== {title} ===")
    groups = defaultdict(Counter)
    for r in rows:
        groups[keyfn(r)][r["action"]] += 1
    hdr = f"{'group':28}" + "".join(f"{a:>9}" for a in actions) + f"{'N':>9}"
    print(hdr)
    print("-" * len(hdr))
    for k in sorted(groups, key=lambda x: str(x)):
        c = groups[k]
        n = sum(c.values())
        row = f"{str(k):28}"
        for a in actions:
            row += f"{100*c[a]/n:>8.1f}%"
        row += f"{n:>9}"
        print(row)


# 1. Preflop scenario x action
pct_table(pf, lambda r: r["pf_scenario"], "PREFLOP: action by scenario")

# 2. face_open sliced by small_open flag
fo = [r for r in pf if r["pf_scenario"] == "face_open"]
pct_table(fo, lambda r: f"small_open={r.get('pf_small_open')}",
          "PREFLOP face_open: action by small_open flag")

# 3. face_open: which branch produced the call/raise
print("\n=== PREFLOP face_open: branch taken (pf_branch) ===")
bc = Counter(r.get("pf_branch") for r in fo)
for k, v in bc.most_common():
    print(f"  {str(k):26} {v:7}  ({100*v/len(fo):.1f}%)")

# 4. face_open calls: how many are equity_override vs table
fo_calls = [r for r in fo if r["action"] == "call"]
print(f"\nface_open calls: {len(fo_calls)}")
print("  ", Counter(r.get("pf_branch") for r in fo_calls))

# 5. Postflop: aggressor vs caller, facing bet or not
def post_key(r):
    role = "aggressor" if r.get("was_pf_aggressor") else "caller"
    face = "facing_bet" if r.get("facing_bet") else "checked_to"
    return f"{role:9} / {face}"
pct_table(post, post_key, "POSTFLOP: action by role x facing-bet")

# 6. Postflop caller, checked-to: does it ever bet (raise) or pure check?
caller_ck = [r for r in post if not r.get("was_pf_aggressor") and not r.get("facing_bet")]
print(f"\nPostflop CALLER, checked-to: N={len(caller_ck)}")
print("  ", Counter(r["action"] for r in caller_ck))

# 7. Postflop caller facing a bet: raise (float/check-raise) vs call vs fold
caller_fb = [r for r in post if not r.get("was_pf_aggressor") and r.get("facing_bet")]
print(f"\nPostflop CALLER, facing a bet: N={len(caller_fb)}")
print("  ", Counter(r["action"] for r in caller_fb))

# 8. Cold-start: action dist by min_hands_obs bucket
def cs_bucket(r):
    m = r.get("min_hands_obs")
    if m is None:
        return "na"
    if m < 6:
        return "0_coldstart(<6)"
    if m < 25:
        return "1_warming(6-24)"
    return "2_exploit(25+)"

pct_table(pf, lambda r: cs_bucket(r), "PREFLOP: action by cold-start bucket")
pct_table([r for r in pf if r["pf_scenario"] == "face_open"],
          lambda r: cs_bucket(r),
          "PREFLOP face_open: action by cold-start bucket")
pct_table(post, lambda r: cs_bucket(r), "POSTFLOP: action by cold-start bucket")
