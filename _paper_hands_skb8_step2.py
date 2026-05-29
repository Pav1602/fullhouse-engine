"""V81 §6.4 — Paper-hand verification for skantbot8 #2 (per-opp narrowing).

For each (opp class, base strength) combination, pre-populates OPPONENTS["opp0"]
with a synthetic profile having a known aggression_factor, then runs
aggressor_likely_range. Verifies the strength-tier shift matches design.

In 7.13 + #1, the strength reaching the narrowing call is always "medium"
or "strong" (never "thin"). So #2's per-opp modifier:
  nit (af<0.5):    "medium" → "strong",  "strong" → "strong"   (narrow MORE)
  median:           unchanged
  maniac (af>1.5): "medium" → "thin",    "strong" → "medium"   (narrow LESS)

Usage:
    python _paper_hands_skb8_step2.py bots/skantbot8/bot.py
"""
import sys, importlib.util
sys.path.insert(0, ".")

BOT_PATH = sys.argv[1] if len(sys.argv) > 1 else "bots/skantbot8/bot.py"


def load_bot(path):
    spec = importlib.util.spec_from_file_location("bot_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def players_6max(skant_seat=2):
    return [
        {"seat": s, "bot_id": ("skant" if s == skant_seat else f"opp{s}"),
         "stack": 10000, "bet_this_street": 0, "is_folded": False,
         "is_all_in": False, "total_invested": 0}
        for s in range(6)
    ]


def state_flop_one_raise(opp_seat, board=("Ks", "7d", "2c")):
    """BTN open → BB call → BB check → BTN bet 50% pot. pf_raises=1, medium tier."""
    return {
        "type": "action_request",
        "seat_to_act": 2,
        "community_cards": list(board),
        "pot": 900,
        "players": players_6max(),
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


def state_flop_three_raises(opp_seat, board=("Ks", "7d", "2c")):
    """Opp's bet then jam (all-in) postflop → strength = strong by all-in path."""
    return {
        "type": "action_request",
        "seat_to_act": 2,
        "community_cards": list(board),
        "pot": 10000,
        "players": players_6max(),
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
            {"seat": 0, "action": "all_in",      "amount": 9700},
        ],
    }


def install_profile(bot, opp_id, hands_observed, af_value):
    """Install profile with a synthetic aggression_factor by setting
    postflop_bets_raises = af_value * postflop_calls."""
    bot.OPPONENTS.clear()
    prof = bot.OPPONENTS[opp_id]
    prof.hands_observed = hands_observed
    prof.postflop_calls = 10
    prof.postflop_bets_raises = int(af_value * 10)
    # Disarm #1 signal so it doesn't interfere: empty bet_size_pcts.
    prof.bet_size_pcts = []


def run(bot, label, state_fn, prof_args, expected_strength):
    install_profile(bot, **prof_args)
    st = state_fn(0)
    for p in st["players"]:
        if p["seat"] == 0:
            p["bot_id"] = prof_args["opp_id"]
    rng = bot.aggressor_likely_range(st, agg_seat=0)
    size = len(rng) if rng else 0
    # Strong: ~13-15; medium: ~24-27; thin (no narrowing): >40
    if expected_strength == "strong":
        ok = size <= 18
    elif expected_strength == "medium":
        ok = 19 <= size <= 30
    else:  # thin → no narrowing
        ok = size >= 35
    flag = "✓" if ok else "✗"
    print(f"  {flag} {label:<55}  size={size:>3}  expect={expected_strength}")
    return ok


def main():
    bot = load_bot(BOT_PATH)
    print(f"Bot: {BOT_PATH}\n")

    # All scenarios use hands_observed=50 (above MIN guard).
    results = []
    NIT     = {"opp_id": "opp0", "hands_observed": 50, "af_value": 0.3}  # < 0.5
    MEDIAN  = {"opp_id": "opp0", "hands_observed": 50, "af_value": 1.0}
    MANIAC  = {"opp_id": "opp0", "hands_observed": 50, "af_value": 2.5}  # > 1.5
    COLD    = {"opp_id": "opp0", "hands_observed": 10, "af_value": 0.3}

    # Base="medium" (single postflop raise on dry K72r):
    results.append(run(bot, "1: medium vs NIT    → strong",
                       state_flop_one_raise, NIT, "strong"))
    results.append(run(bot, "2: medium vs MEDIAN → medium (unchanged)",
                       state_flop_one_raise, MEDIAN, "medium"))
    results.append(run(bot, "3: medium vs MANIAC → thin (no narrowing)",
                       state_flop_one_raise, MANIAC, "thin"))

    # Base="strong" (3+ postflop raises):
    results.append(run(bot, "4: strong vs NIT    → strong (unchanged)",
                       state_flop_three_raises, NIT, "strong"))
    results.append(run(bot, "5: strong vs MEDIAN → strong (unchanged)",
                       state_flop_three_raises, MEDIAN, "strong"))
    results.append(run(bot, "6: strong vs MANIAC → medium (loosened)",
                       state_flop_three_raises, MANIAC, "medium"))

    # Cold-start: < MIN_HANDS_PER_OPP → no modifier
    results.append(run(bot, "7: cold-start (10 hands) → medium (no modifier)",
                       state_flop_one_raise, COLD, "medium"))

    n_pass = sum(results)
    print(f"\n{n_pass}/{len(results)} paper hands match prediction.")
    if n_pass != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
