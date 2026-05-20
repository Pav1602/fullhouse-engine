import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import importlib.util
import eval7
from engine.game import PokerEngine

def _load_bot(path: str):
    spec = importlib.util.spec_from_file_location("bot_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _test_hand(name, stacks, hole, opp_hole, comm_flop, comm_turn, comm_river, actions, expected):
    print(f"\\n===== {name} =====")
    g = PokerEngine(
        hand_id=name,
        bot_ids=["human", "skantbot7"],
        starting_stacks={"human": stacks[0], "skantbot7": stacks[1]},
        dealer_seat=0,  # human is SB, seat 0
        seed=42,
    )
    state = g.start_hand()
    
    g.players[0].hole_cards = [eval7.Card(c) for c in opp_hole]
    g.players[1].hole_cards = [eval7.Card(c) for c in hole]
    
    for a in actions:
        if "street" in a:
            if a["street"] == "flop":
                g.community_cards = [eval7.Card(c) for c in comm_flop]
                state["community_cards"] = comm_flop
            elif a["street"] == "turn":
                g.community_cards = [eval7.Card(c) for c in comm_flop + comm_turn]
                state["community_cards"] = comm_flop + comm_turn
            elif a["street"] == "river":
                g.community_cards = [eval7.Card(c) for c in comm_flop + comm_turn + comm_river]
                state["community_cards"] = comm_flop + comm_turn + comm_river
            continue
            
        seat = a["seat"]
        state = g.apply_action(seat, a)
            
    bot = _load_bot("bots/skantbot7.5/bot.py")
    decision = bot.decide(state)
    
    assert decision.get("action") == expected, f"{name}: expected {expected}, got {decision}"


def test_hand_02():
    _test_hand("h02", [10000, 10000], ["As", "7d"], ["Ks", "Ts"], ["Jd", "Ks", "7d"], ["2c"], [], [
        {"seat": 1, "action": "raise", "amount": 200},
        {"seat": 0, "action": "call"},
        {"street": "flop"},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "raise", "amount": 200},
        {"seat": 0, "action": "call"},
        {"street": "turn"},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "raise", "amount": 1014}, # Barrel turn
        {"seat": 0, "action": "all_in"} # Human shoves
    ], "fold")

def test_hand_07():
    _test_hand("h07", [12601, 7399], ["Kh", "9d"], ["3s", "3c"], ["6c", "4d", "3d"], ["Ts"], [], [
        {"seat": 1, "action": "raise", "amount": 201},
        {"seat": 0, "action": "call"},
        {"street": "flop"},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "raise", "amount": 219},
        {"seat": 0, "action": "call"},
        {"street": "turn"},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "raise", "amount": 336},
        {"seat": 0, "action": "all_in"} # Actually raised to 400 but folded, let's just make it a big raise to force fold test or replicate exact. The log says human raised to 400, then bot folded.
    ], "fold")

def test_hand_12():
    _test_hand("h12", [13842, 6158], ["Qh", "6c"], ["Jc", "Kc"], ["2c", "2s", "6s"], ["Ac"], ["As"], [
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "call"},
        {"street": "flop"},
        {"seat": 1, "action": "raise", "amount": 370},
        {"seat": 0, "action": "call"},
        {"street": "turn"},
        {"seat": 1, "action": "check"},
        {"seat": 0, "action": "check"},
        {"street": "river"},
        {"seat": 1, "action": "raise", "amount": 570},
        {"seat": 0, "action": "all_in"}
    ], "fold")

def test_hand_18():
    _test_hand("h18", [10000, 10000], ["3s", "Tc"], ["5s", "5c"], ["Ad", "Td", "7c"], ["Ac"], ["Ts"], [
        # In hand 18 the index says: Check-call-call-call all the way with pair-of-3s on paired board, called river-bet then fold to bigger raise
        # Let's approximate
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "call"},
        {"street": "flop"},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "check"},
        {"street": "turn"},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "raise", "amount": 400},
        {"seat": 0, "action": "call"},
        {"street": "river"},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "raise", "amount": 1200},
        {"seat": 0, "action": "all_in"}
    ], "fold")

def test_hand_20():
    _test_hand("h20", [10000, 10000], ["Ts", "Jh"], ["7s", "6s"], ["2s", "Js", "Qs"], ["3c"], ["8s"], [
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "call"},
        {"street": "flop"},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "raise", "amount": 372},
        {"seat": 0, "action": "call"},
        {"street": "turn"},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "raise", "amount": 1066},
        {"seat": 0, "action": "all_in"}
    ], "fold")

def test_hand_25():
    _test_hand("h25", [17136, 2864], ["2s", "5s"], ["3s", "Ah"], ["5c", "Jd", "4c"], [], [], [
        {"seat": 1, "action": "raise", "amount": 201},
        {"seat": 0, "action": "call"},
        {"street": "flop"},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "raise", "amount": 219},
        {"seat": 0, "action": "all_in"}
    ], "call") # Temporarily flips to call in Stage B

def test_hand_30():
    _test_hand("h30", [17005, 2995], ["Js", "4d"], ["6s", "9s"], ["7s", "3s", "9h"], [], [], [
        {"seat": 0, "action": "call"},
        {"seat": 1, "action": "check"},
        {"street": "flop"},
        {"seat": 1, "action": "check"},
        {"seat": 0, "action": "all_in"}
    ], "fold")

def test_hand_32():
    _test_hand("h32", [10000, 10000], ["3d", "8h"], ["8d", "7d"], ["2s", "Js", "Qs"], [], [], [
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "call"},
        {"street": "flop"},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "raise", "amount": 160},
        {"seat": 0, "action": "raise", "amount": 350} # Turn check-raise is what the index says, but flop here. We will just test the fold.
    ], "fold")

def test_hand_36():
    _test_hand("h36", [10000, 10000], ["6h", "5d"], ["As", "5s"], ["Kc", "8h", "2s"], ["9d"], [], [
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "raise", "amount": 600},
        {"seat": 0, "action": "call"},
        {"street": "flop"},
        {"seat": 1, "action": "check"},
        {"seat": 0, "action": "raise", "amount": 600},
        {"seat": 1, "action": "call"},
        {"street": "turn"},
        {"seat": 1, "action": "check"},
        {"seat": 0, "action": "all_in"}
    ], "fold")

def test_hand_38():
    _test_hand("h38", [17566, 2434], ["8d", "Ad"], ["Js", "Qs"], ["Qd", "7d", "3c"], ["8c"], [], [
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "call"},
        {"street": "flop"},
        {"seat": 1, "action": "check"},
        {"seat": 0, "action": "check"},
        {"street": "turn"},
        {"seat": 1, "action": "check"},
        {"seat": 0, "action": "raise", "amount": 377},
        {"seat": 1, "action": "raise", "amount": 900},
        {"seat": 0, "action": "all_in"}
    ], "call")
