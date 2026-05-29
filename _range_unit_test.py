"""V81 §3.1c — Aggressor range unit test.

For a fixed set of canonical (state, agg_seat) scenarios, call
`aggressor_likely_range(state, agg_seat)` on a given bot.py and print the
resulting range size + top hands. Diffs across bot versions are the proof
that a structural change actually affected range narrowing.

Usage:
    python _range_unit_test.py bots/skantbot7.13/bot.py
    python _range_unit_test.py bots/skantbot8/bot.py
"""
import sys, importlib.util, json
sys.path.insert(0, ".")

BOT_PATH = sys.argv[1] if len(sys.argv) > 1 else "bots/skantbot7.13/bot.py"
OUT_PATH = sys.argv[2] if len(sys.argv) > 2 else None


def load_bot(path):
    spec = importlib.util.spec_from_file_location("bot_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def players_6max(skant_seat=0, opp_seats_with_id=()):
    """Build the public players list. Skant occupies skant_seat; named opps
    populate the rest. Default opp names just mark seats."""
    names = {skant_seat: "skant"}
    for seat, oid in opp_seats_with_id:
        names[seat] = oid
    return [
        {"seat": s, "bot_id": names.get(s, f"opp{s}"),
         "stack": 10000, "bet_this_street": 0, "is_folded": False,
         "is_all_in": False, "total_invested": 0}
        for s in range(6)
    ]


# ---------------------------------------------------------------------------
# Canonical scenarios — list of dicts:
#   {"label": ..., "state": ..., "agg_seat": ..., "notes": ...}
# Each scenario isolates a branch the structural changes target.
# ---------------------------------------------------------------------------

SCENARIOS = []


def scenario(label, state, agg_seat, notes=""):
    SCENARIOS.append({"label": label, "state": state, "agg_seat": agg_seat,
                      "notes": notes})


# ---- S1 — Preflop SB vs BTN 3-bet pot, BB folded, hero (BB) to act --------
# 6-max blinds 50/100. BTN open to 2bb=200, SB 3-bet to 600. Hero in BB,
# action back on hero. aggressor=SB(seat=1).
state_s1 = {
    "type": "action_request",
    "seat_to_act": 2,                           # hero BB
    "community_cards": [],
    "pot": 50 + 100 + 200 + 600,
    "players": players_6max(skant_seat=2),
    "action_log": [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 2, "action": "big_blind",   "amount": 100},
        {"seat": 3, "action": "fold",        "amount": 0},
        {"seat": 4, "action": "fold",        "amount": 0},
        {"seat": 5, "action": "fold",        "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 200},
        {"seat": 1, "action": "raise",       "amount": 600},
    ],
}
scenario("S1 preflop SB-3bet, hero BB", state_s1, agg_seat=1,
         notes="3-bettor branch; range = THREEBET_FREQS[(SB, BTN)]")


# ---- S2 — Flop dry K72r, opp bet 50% pot (no commitment-tier yet) ---------
# 6-max BTN open + BB call. Hero BB checks. BTN bet 300 into 600 pot (50%).
state_s2 = {
    "type": "action_request",
    "seat_to_act": 2,                           # hero BB
    "community_cards": ["Ks", "7d", "2c"],
    "pot": 600 + 300,
    "players": players_6max(skant_seat=2),
    "action_log": [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 2, "action": "big_blind",   "amount": 100},
        {"seat": 3, "action": "fold",        "amount": 0},
        {"seat": 4, "action": "fold",        "amount": 0},
        {"seat": 5, "action": "fold",        "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 300},
        {"seat": 1, "action": "fold",        "amount": 0},
        {"seat": 2, "action": "call",        "amount": 200},
        {"seat": 2, "action": "check",       "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 300},
    ],
}
scenario("S2 flop dry, opp half-pot bet", state_s2, agg_seat=0,
         notes="postflop_raises=1, strength=medium; #1 should NOT fire if bet/pot < threshold")


# ---- S3 — Flop dry K72r, opp bet 100% pot (commitment-tier bet) ----------
state_s3 = {
    "type": "action_request",
    "seat_to_act": 2,
    "community_cards": ["Ks", "7d", "2c"],
    "pot": 600 + 600,
    "players": players_6max(skant_seat=2),
    "action_log": [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 2, "action": "big_blind",   "amount": 100},
        {"seat": 3, "action": "fold",        "amount": 0},
        {"seat": 4, "action": "fold",        "amount": 0},
        {"seat": 5, "action": "fold",        "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 300},
        {"seat": 1, "action": "fold",        "amount": 0},
        {"seat": 2, "action": "call",        "amount": 200},
        {"seat": 2, "action": "check",       "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 600},
    ],
}
scenario("S3 flop dry, opp full-pot bet", state_s3, agg_seat=0,
         notes="postflop_raises=1, bet/pot=1.0; #1 RELATIVE signal should fire IF opp has bet history")


# ---- S4 — Turn, opp jam (all-in) — already strong tier --------------------
state_s4 = {
    "type": "action_request",
    "seat_to_act": 2,
    "community_cards": ["Ks", "7d", "2c", "9h"],
    "pot": 1200 + 9700,
    "players": players_6max(skant_seat=2),
    "action_log": [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 2, "action": "big_blind",   "amount": 100},
        {"seat": 3, "action": "fold",        "amount": 0},
        {"seat": 4, "action": "fold",        "amount": 0},
        {"seat": 5, "action": "fold",        "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 300},
        {"seat": 1, "action": "fold",        "amount": 0},
        {"seat": 2, "action": "call",        "amount": 200},
        {"seat": 2, "action": "check",       "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 600},
        {"seat": 2, "action": "call",        "amount": 600},
        {"seat": 2, "action": "check",       "amount": 0},
        {"seat": 0, "action": "all_in",      "amount": 9700},
    ],
}
scenario("S4 turn opp jam", state_s4, agg_seat=0,
         notes="all-in fast-path → strength=strong regardless")


# ---- S5 — Flop wet T98ss, opp bet 100% pot --------------------------------
state_s5 = {
    "type": "action_request",
    "seat_to_act": 2,
    "community_cards": ["Ts", "9s", "8d"],
    "pot": 600 + 600,
    "players": players_6max(skant_seat=2),
    "action_log": [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 2, "action": "big_blind",   "amount": 100},
        {"seat": 3, "action": "fold",        "amount": 0},
        {"seat": 4, "action": "fold",        "amount": 0},
        {"seat": 5, "action": "fold",        "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 300},
        {"seat": 1, "action": "fold",        "amount": 0},
        {"seat": 2, "action": "call",        "amount": 200},
        {"seat": 2, "action": "check",       "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 600},
    ],
}
scenario("S5 flop wet, opp full-pot bet", state_s5, agg_seat=0,
         notes="like S3 but wet board — control")


# ---- S6 — Flop paired board K72r-K, opp bet (paired→strong already) -------
state_s6 = {
    "type": "action_request",
    "seat_to_act": 2,
    "community_cards": ["Ks", "Kd", "7c"],
    "pot": 600 + 300,
    "players": players_6max(skant_seat=2),
    "action_log": [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 2, "action": "big_blind",   "amount": 100},
        {"seat": 3, "action": "fold",        "amount": 0},
        {"seat": 4, "action": "fold",        "amount": 0},
        {"seat": 5, "action": "fold",        "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 300},
        {"seat": 1, "action": "fold",        "amount": 0},
        {"seat": 2, "action": "call",        "amount": 200},
        {"seat": 2, "action": "check",       "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 300},
    ],
}
scenario("S6 flop paired, opp half-pot bet", state_s6, agg_seat=0,
         notes="paired board already maps to strength=strong via existing logic")


# ---- S7 — Turn, two postflop raises (escalating action) -------------------
state_s7 = {
    "type": "action_request",
    "seat_to_act": 2,
    "community_cards": ["Ks", "7d", "2c", "9h"],
    "pot": 4000,
    "players": players_6max(skant_seat=2),
    "action_log": [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 2, "action": "big_blind",   "amount": 100},
        {"seat": 3, "action": "fold",        "amount": 0},
        {"seat": 4, "action": "fold",        "amount": 0},
        {"seat": 5, "action": "fold",        "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 300},
        {"seat": 1, "action": "fold",        "amount": 0},
        {"seat": 2, "action": "call",        "amount": 200},
        {"seat": 2, "action": "check",       "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 500},
        {"seat": 2, "action": "call",        "amount": 500},
        {"seat": 2, "action": "check",       "amount": 0},
        {"seat": 0, "action": "raise",       "amount": 1000},
    ],
}
scenario("S7 turn, two postflop raises", state_s7, agg_seat=0,
         notes="postflop_raises=2 → strength=medium; chain progression")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def summarize_range(rng_dict, top_n=8):
    if not rng_dict:
        return {"size": 0, "top": [], "total_freq": 0.0}
    items = sorted(rng_dict.items(), key=lambda kv: -kv[1])
    return {
        "size": len(items),
        "total_freq": round(sum(rng_dict.values()), 3),
        "top": [(h, round(f, 3)) for h, f in items[:top_n]],
    }


def main():
    bot = load_bot(BOT_PATH)
    print(f"Bot: {BOT_PATH}")
    out = {"bot": BOT_PATH, "scenarios": []}
    for sc in SCENARIOS:
        try:
            rng = bot.aggressor_likely_range(sc["state"], sc["agg_seat"])
        except Exception as e:
            rng = {"__error__": f"{type(e).__name__}: {e}"}
        if isinstance(rng, dict) and "__error__" in rng:
            print(f"  {sc['label']:<42}  ERROR: {rng['__error__']}")
            out["scenarios"].append({"label": sc["label"], "error": rng["__error__"]})
            continue
        s = summarize_range(rng)
        print(f"  {sc['label']:<42}  size={s['size']:>4}  "
              f"sum_freq={s['total_freq']:>5}  top={s['top'][:4]}")
        out["scenarios"].append({
            "label": sc["label"], "agg_seat": sc["agg_seat"],
            "notes": sc["notes"],
            "summary": s,
        })

    if OUT_PATH:
        with open(OUT_PATH, "w") as f:
            json.dump(out, f, indent=2)
        print(f"Saved: {OUT_PATH}")


if __name__ == "__main__":
    main()
