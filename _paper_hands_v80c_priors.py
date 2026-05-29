"""Paper hands testing each V80c candidate prior shift against 3 bust hands.

For each bust hand, replay the bot's decisions with:
  A. baseline 7.13 (control)
  B. equity_call_threshold 0.39 → 0.45 (advisor recommendation)
  C. equity_thin_value 0.48 → 0.55 (advisor: missing key param)
  D. bluff_freq_oop 0.039 → 0.02 (V80b prior)
  E. pot_odds_buffer_normal 0.10 → 0.15 (advisor)
  F. k_commit 0.005 → 0.001 (advisor: probably should LOWER)
  G. all 5 combined

Check if the bust pattern (donk-lead/call-then-fold) gets short-circuited.
"""
import sys, importlib.util, copy
sys.path.insert(0, ".")

# Bust hands — (label, action_log up to each decision)
# Reconstructed from harness/results/bust_survey_skantbot7.13_heldout_n100.json

# All three have skant donk-leading 3 streets, ending with river fold
# bust_036_h0122: skant in BB defends limp, donks Ac-Qc-6h
# bust_036_h0082: skant in BB defends limp, donks 5s-Tc-6c
# bust_016_h0030: skant in BB defends a raise (s2r200), donks Kh-4c-4h

BUSTS = [
    {
        "label": "bust_036_h0122 (Ac-Qc-6h vs super_nit)",
        "hole": ["Ah", "4d"],  # unknown; A4o defensible BB defend
        "board_final": ["Ac", "Qc", "6h", "3s", "2d"],
        "stacks_start": 10000,
        "preflop_log": [
            {"seat": 3, "action": "small_blind", "amount": 50},
            {"seat": 0, "action": "big_blind",   "amount": 100},
            {"seat": 1, "action": "fold",        "amount": 0},
            {"seat": 2, "action": "call",        "amount": 100},
            {"seat": 3, "action": "fold",        "amount": 0},
        ],
        "decisions": [
            ("preflop_check", "preflop", [], 100, 100, 9900, 0),
            ("flop_can_check", "flop", ["Ac","Qc","6h"], 0, 0, 9900, 0),
            ("flop_facing_490", "flop", ["Ac","Qc","6h"], 490, 240, 9660, 250),
            ("turn_can_check", "turn", ["Ac","Qc","6h","3s"], 0, 0, 9410, 0),
            ("turn_facing_2414", "turn", ["Ac","Qc","6h","3s"], 2414, 1184, 8226, 1230),
            ("river_can_check", "river", ["Ac","Qc","6h","3s","2d"], 0, 0, 6996, 0),
            ("river_facing_9087", "river", ["Ac","Qc","6h","3s","2d"], 9087, 3029, 3967, 6058),
        ],
        "actual_log": [
            ("raise", 240), ("call", 250), ("raise", 1184), ("call", 1230), ("raise", 3029), ("fold", 0),
        ],
    },
]

OVERRIDES = {
    "A_baseline": {},
    "B_eq_call_up": {"equity_call_threshold": 0.45},
    "C_thin_up":   {"equity_thin_value": 0.55},
    "D_bluff_dn":  {"bluff_freq_oop": 0.02},
    "E_pot_buf_up":{"pot_odds_buffer_normal": 0.15},
    "F_k_commit_dn":{"k_commit": 0.001},
    "G_combined":  {
        "equity_call_threshold": 0.45,
        "equity_thin_value": 0.55,
        "bluff_freq_oop": 0.02,
        "pot_odds_buffer_normal": 0.15,
        "k_commit": 0.001,
    },
}


def load_fresh_bot():
    spec = importlib.util.spec_from_file_location("b", "bots/skantbot7.13/bot.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def build_state(bust, dec, action_log_so_far):
    label, street, board, current_bet, your_bet_this_street, your_stack, owed = dec
    return {
        "type": "action_request",
        "hand_id": f"paper_{bust['label'].split()[0]}_{label}",
        "street": street,
        "seat_to_act": 0,
        "pot": sum(e.get("amount", 0) for e in action_log_so_far),
        "community_cards": list(board),
        "current_bet": current_bet,
        "min_raise_to": current_bet * 2,
        "amount_owed": owed,
        "can_check": owed == 0,
        "your_cards": list(bust["hole"]),
        "your_stack": your_stack,
        "your_bet_this_street": your_bet_this_street,
        "players": [
            {"seat": i, "bot_id": f"opp{i}" if i != 0 else "skant",
             "is_folded": (i in (1, 3)),
             "is_all_in": False,
             "stack": your_stack if i == 0 else 9900}
            for i in range(5)
        ],
        "action_log": list(action_log_so_far),
    }


def run_paper_hand(bust, override_name, overrides):
    """Run all decision points in this hand with overrides applied, report actions."""
    bot = load_fresh_bot()
    for k, v in overrides.items():
        setattr(bot.CONFIG, k, v)

    action_log = list(bust["preflop_log"])
    actions = []
    for i, dec in enumerate(bust["decisions"]):
        label = dec[0]
        state = build_state(bust, dec, action_log)
        action = bot.decide(state)
        actions.append((label, action))
        # Append the actual opp action that followed in real hand
        if i < len(bust["actual_log"]):
            real_act, real_amt = bust["actual_log"][i]
            # Skant did this action
            action_log.append({"seat": 0, "action": real_act, "amount": real_amt})
            # Then opp responded — synthesize from final board / log structure
            # For simplicity, mirror real bust's opp actions
            opp_action_seq = [
                (2, "raise", 490),   # flop raise
                None,                 # call advance (no opp action)
                (2, "raise", 2414),  # turn raise
                None,
                (2, "raise", 9087),  # river raise
                None,
            ]
            if i < len(opp_action_seq) and opp_action_seq[i] is not None:
                seat, a, amt = opp_action_seq[i]
                action_log.append({"seat": seat, "action": a, "amount": amt})
    return actions


for bust in BUSTS:
    print(f"\n{'='*78}")
    print(f"PAPER HAND: {bust['label']}")
    print(f"Hole: {bust['hole']}, board final: {bust['board_final']}")
    print('='*78)
    print(f"\nActual bust line: skant donk 240 → call 250 → donk 1184 → call 1230 → donk 3029 → fold 6058 ($6,033 lost)")
    print(f"\n{'override':<18} | {'preflop':<14} | {'flop_donk':<14} | {'flop_call':<14} | {'turn_donk':<14} | {'turn_call':<14} | {'river_donk':<14} | {'river_fold':<14}")
    print('-' * 142)
    for name, overrides in OVERRIDES.items():
        actions = run_paper_hand(bust, name, overrides)
        line = f"{name:<18}"
        for label, act in actions:
            short = act.get("action", "?")[:5]
            amt = act.get("amount", "")
            if amt: short = f"{short[:4]}{amt}"
            line += f" | {short:<14}"
        print(line)
