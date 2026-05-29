"""Parametrized bust survey. Usage:
  python _bust_survey_param.py <bot_id> <bot_path> <pool_type> [n_matches]

pool_type: train | heldout | combined
"""
import sys, os, json, random
sys.path.insert(0, ".")
from sandbox.match import run_match, STARTING_STACK
from harness.opponents.registry import load_pool

SKANT = sys.argv[1]
SKANT_PATH = sys.argv[2]
POOL_TYPE = sys.argv[3] if len(sys.argv) > 3 else "train"
N_MATCHES = int(sys.argv[4]) if len(sys.argv) > 4 else 100
N_HANDS = 200
LOSS_THRESHOLD = 2000

if POOL_TYPE == "train":
    pool = load_pool(include_heldout=False)
elif POOL_TYPE == "heldout":
    full = load_pool(include_heldout=True)
    train = load_pool(include_heldout=False)
    pool = {k: v for k, v in full.items() if k not in train}
else:
    pool = load_pool(include_heldout=True)

pool_items = list(pool.items())
print(f"Surveying {SKANT} against {POOL_TYPE} pool ({len(pool)} opps), {N_MATCHES} matches × {N_HANDS} hands")

# Import classify helpers from _bust_analyze
import importlib.util
ba_spec = importlib.util.spec_from_file_location("_ba", "_bust_analyze.py")
ba = importlib.util.module_from_spec(ba_spec); ba_spec.loader.exec_module(ba)

random.seed(42)
all_busts = []
total_loss = 0
total_hands = 0
for i in range(N_MATCHES):
    seed = random.randint(0, 1_000_000)
    opps = random.sample(pool_items, min(5, len(pool_items)))
    bots = {SKANT: SKANT_PATH}
    for oid, opath in opps:
        bots[oid] = opath
    res = run_match(f"survey_{i:03d}", bots, n_hands=N_HANDS, seed=seed)
    skant_stack = STARTING_STACK
    for h in res["hands"]:
        post = h["final_stacks"].get(SKANT, skant_stack)
        delta = post - skant_stack
        if delta <= -LOSS_THRESHOLD:
            classification = ba.classify_bust(h, SKANT)
            classification.update({
                "match_idx": i, "hand_num": h["hand_num"], "hand_id": h["hand_id"],
                "pre_stack": skant_stack, "post_stack": post, "loss": -delta,
                "final_street": h.get("street", "?"),
                "board": h.get("community_cards", []),
                "n_board": len(h.get("community_cards", [])),
                "action_log": h.get("action_log", []),
                "opp_set": [o for o, _ in opps],
            })
            all_busts.append(classification)
            total_loss += -delta
        skant_stack = post
        total_hands += 1
    if (i+1) % 20 == 0:
        print(f"  match {i+1}/{N_MATCHES}: cum_busts={len(all_busts)}, cum_loss=${total_loss:,}")

out_path = f"harness/results/bust_survey_{SKANT}_{POOL_TYPE}_n{N_MATCHES}.json"
with open(out_path, "w") as f:
    json.dump({
        "n_matches": N_MATCHES, "n_hands_per": N_HANDS,
        "total_hands": total_hands, "n_busts": len(all_busts),
        "total_loss": total_loss, "busts": all_busts,
    }, f)
print(f"\n{SKANT} on {POOL_TYPE}: {len(all_busts)} busts, ${total_loss:,} loss over {total_hands} hands")
print(f"Saved: {out_path}")
