"""Per-decision trace of bust_036_h0122 through 7.13, 7.9, and 7.14.

For each of skant's decisions in this hand, reconstruct the state at that
decision point and call each bot's decide(). Capture:
  - which branch fired (via SKANT_LOG_PATH)
  - eq estimate
  - aggressor_likely_range size + sample
  - opp_postflop_raises this hand
  - bot's chosen action

This is the diagnostic we should have run BEFORE proposing any fix.
"""
import sys, os, json, importlib.util, random
sys.path.insert(0, ".")

# Constants
INITIAL_STACK = 10000
SB_AMT = 50
BB_AMT = 100

# Bust 036_h0122 action log — skant is s0, super_nit is s2
# Five-handed start; s1 folds preflop, s3 folds preflop, s4 inactive
# board Ac-Qc-6h-3s-2d
HAND_LOG = [
    {"seat": 3, "action": "small_blind", "amount": 50},
    {"seat": 0, "action": "big_blind",   "amount": 100},
    {"seat": 1, "action": "fold",        "amount": 0},
    {"seat": 2, "action": "call",        "amount": 100},
    {"seat": 3, "action": "fold",        "amount": 0},
    {"seat": 0, "action": "check",       "amount": 0},     # skant BB checks pre
    # FLOP Ac-Qc-6h
    {"seat": 0, "action": "raise",       "amount": 240},   # skant DONK-LEAD
    {"seat": 2, "action": "raise",       "amount": 490},   # super_nit raises
    {"seat": 0, "action": "call",        "amount": 250},   # skant calls
    # TURN 3s
    {"seat": 0, "action": "raise",       "amount": 1184},  # skant DONK-LEAD again
    {"seat": 2, "action": "raise",       "amount": 2414},  # super_nit raises
    {"seat": 0, "action": "call",        "amount": 1230},  # skant calls
    # RIVER 2d
    {"seat": 0, "action": "raise",       "amount": 3029},  # skant DONK-LEAD third street
    {"seat": 2, "action": "raise",       "amount": 9087},  # super_nit raises huge
    {"seat": 0, "action": "fold",        "amount": 0},     # skant folds (bust)
]

# skant's hole — let's pick a hand consistent with bust pattern (high VPIP from BB)
# A4o is a defensible BB defense
SKANT_HOLE = ["Ah", "4d"]

# Skant's decision indices in HAND_LOG (each is a check/raise by s0)
DECISION_INDICES = [5, 6, 8, 9, 11, 12, 14]


def build_state_at(idx, board, current_bet, your_bet_this_street, your_stack, owed, street):
    return {
        "type": "action_request",
        "hand_id": "bust_survey_036_h0122",  # exact hand_id from bust survey — same rng seed
        "street": street,
        "seat_to_act": 0,
        "pot": sum(e.get("amount", 0) for e in HAND_LOG[:idx]),
        "community_cards": list(board),
        "current_bet": current_bet,
        "min_raise_to": current_bet * 2,
        "amount_owed": owed,
        "can_check": owed == 0,
        "your_cards": list(SKANT_HOLE),
        "your_stack": your_stack,
        "your_bet_this_street": your_bet_this_street,
        "players": [
            {"seat": i, "bot_id": f"opp{i}" if i != 0 else "skant",
             "is_folded": (i in (1, 3)),
             "is_all_in": False,
             "stack": your_stack if i == 0 else 9900}
            for i in range(5)
        ],
        "action_log": HAND_LOG[:idx],
    }


# Decision points with state context (manually computed from log)
# Format: (idx, label, board, current_bet, your_bet_this_street, your_stack, owed, street)
DECISIONS = [
    (5,  "preflop: BB facing limp, can check",      [], 100, 100, 9900, 0, "preflop"),
    (6,  "flop: OOP, can check, decides DONK 240",  ["Ac", "Qc", "6h"], 0, 0, 9900, 0, "flop"),
    (8,  "flop: facing opp raise 490, owes 250",    ["Ac", "Qc", "6h"], 490, 240, 9660, 250, "flop"),
    (9,  "turn: OOP, can check, decides DONK 1184", ["Ac", "Qc", "6h", "3s"], 0, 0, 9410, 0, "turn"),
    (11, "turn: facing opp raise 2414, owes 1230",  ["Ac", "Qc", "6h", "3s"], 2414, 1184, 8226, 1230, "turn"),
    (12, "river: OOP, can check, decides DONK 3029",["Ac", "Qc", "6h", "3s", "2d"], 0, 0, 6996, 0, "river"),
    (14, "river: facing opp raise 9087, owes 6058", ["Ac", "Qc", "6h", "3s", "2d"], 9087, 3029, 3967, 6058, "river"),
]


def load_bot(path):
    spec = importlib.util.spec_from_file_location(f"bot_{abs(hash(path))}", path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def trace_bot(bot, label, state, log_path):
    # Reset state
    if hasattr(bot, "reset_match_state"):
        bot.reset_match_state()
    bot.CONFIG.log_path = log_path
    # Clear log file
    try: os.remove(log_path)
    except FileNotFoundError: pass
    # Call decide
    action = bot.decide(state)
    # Read log
    log_entry = None
    try:
        with open(log_path) as f:
            lines = f.readlines()
        if lines:
            log_entry = json.loads(lines[-1])
    except Exception:
        pass
    # Inspect intermediate state
    me = state.get("seat_to_act")
    pf_log = bot._preflop_action_log(state)
    pf_len = len(pf_log)
    opp_pf_raises = sum(1 for e in state.get("action_log", [])[pf_len:]
                        if e.get("action") in ("raise", "all_in")
                        and e.get("seat") != me)
    agg_seat = bot.find_aggressor_seat(state)
    range_size = "—"
    eq_str = "—"
    if state.get("street") != "preflop" and agg_seat is not None:
        try:
            v_range = bot.aggressor_likely_range(state, agg_seat)
            range_size = f"{len(v_range)} hands"
            board = state.get("community_cards", [])
            n_sims = 100  # quick
            rng = bot.get_hand_rng(state)
            if board and len(board) >= 3:
                eq = bot.equity_vs_range(state["your_cards"], board, v_range, n_sims=n_sims, rng=rng)
                eq_str = f"{eq:.3f}"
        except Exception as e:
            range_size = f"ERR: {e}"
    print(f"  {label}: action={action}  branch={log_entry.get('branch') if log_entry else 'N/A'}")
    print(f"    eq={eq_str}  range_size={range_size}  opp_pf_raises={opp_pf_raises}")
    print(f"    pot={state['pot']}  owed={state['amount_owed']}  stack={state['your_stack']}")


if __name__ == "__main__":
    b13 = load_bot("harness/skantbot7_13_dev/bot.py")
    b9 = load_bot("bots/skantbot7.9/bot.py")
    b14 = load_bot("harness/skantbot7_14_dev/bot.py")

    print(f"BUST 036_h0122 TRACE — skant hole={SKANT_HOLE}, board final=[Ac,Qc,6h,3s,2d]")
    print(f"super_nit (s2) raised on flop, turn, and river. skant donk-led each street.\n")

    for idx, label, board, cb, ybt, stack, owed, street in DECISIONS:
        state = build_state_at(idx, board, cb, ybt, stack, owed, street)
        print(f"\n=== {label} ===")
        trace_bot(b13, "7.13", state, "/tmp/trace_713.jsonl")
        trace_bot(b9,  "7.9 ", state, "/tmp/trace_79.jsonl")
        trace_bot(b14, "7.14", state, "/tmp/trace_714.jsonl")
