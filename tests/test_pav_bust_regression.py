import sys
import importlib.util

def _load_bot(path: str):
    spec = importlib.util.spec_from_file_location("bot_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _build_state(hand_id: str, hole: list, board: list, log: list, pot: int, owed: int, current_bet: int, can_check: bool, stack: int, seat: int = 0, is_oop: bool = False):
    return {
        "type": "action_request",
        "hand_id": hand_id,
        "street": "river" if len(board) == 5 else "turn" if len(board) == 4 else "flop" if len(board) == 3 else "preflop",
        "seat_to_act": seat,
        "pot": pot,
        "community_cards": board,
        "current_bet": current_bet,
        "amount_owed": owed,
        "can_check": can_check,
        "your_cards": hole,
        "your_stack": stack,
        "your_bet_this_street": 0,
        "players": [
            {"seat": seat, "state": "active", "is_folded": False, "is_all_in": False},
            {"seat": 1 - seat, "state": "active", "is_folded": False, "is_all_in": False}
        ],
        "action_log": log
    }

def test_hand_02():
    # Bot opens 200, Pav calls. Flop [As 2d Qc]. Bot checks. Pav bets 200. Bot calls.
    # Turn [Js]. Bot checks. Pav bets 800. Bot folds KT (gutshot + King high).
    # Expected: Fold is correct.
    state = _build_state("h02", ["Ks", "Ts"], ["As", "2d", "Qc", "Js"], [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 0, "action": "big_blind", "amount": 100},
        {"seat": 1, "action": "raise", "amount": 200},
        {"seat": 0, "action": "call", "amount": 100},
        {"seat": 1, "action": "check", "amount": 0},
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "call", "amount": 200},
        {"seat": 1, "action": "check", "amount": 0},
        {"seat": 0, "action": "raise", "amount": 800}
    ], pot=800, owed=800, current_bet=800, can_check=False, stack=9600, seat=1)
    
    bot = _load_bot("bots/skantbot7.4/bot.py")
    decision = bot.decide(state)
    assert decision.get("action") == "fold", f"Expected fold on h02, got {decision}"

def test_hand_07():
    # Pav opens 200. Bot calls (QJo). Flop [Kd Qh Td]. Pav bets 200, Bot calls.
    # Turn [3d]. Pav bets 800, Bot calls.
    # River [Th]. Pav shoves 8800. Bot folds. (Middle pair, 4-flush board).
    # Expected: Fold is correct.
    state = _build_state("h07", ["Qh", "Jc"], ["Kd", "Qh", "Td", "3d", "Th"], [
        {"seat": 0, "action": "small_blind", "amount": 50},
        {"seat": 1, "action": "big_blind", "amount": 100},
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "call", "amount": 100},
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "call", "amount": 200},
        {"seat": 0, "action": "raise", "amount": 800},
        {"seat": 1, "action": "call", "amount": 800},
        {"seat": 0, "action": "raise", "amount": 8800}
    ], pot=2400, owed=8800, current_bet=8800, can_check=False, stack=8800, seat=1)
    
    bot = _load_bot("bots/skantbot7.4/bot.py")
    decision = bot.decide(state)
    assert decision.get("action") == "fold", f"Expected fold on h07, got {decision}"

def test_hand_12():
    # Bot opens 200, Pav 3-bets 600. Bot calls 87s.
    # Flop [Jd 6d 7c]. Pav bets 600, Bot calls.
    # Turn [6s]. Pav bets 1200, Bot calls.
    # River [As]. Pav shoves 7600. Bot folds (2nd pair).
    # Expected: Fold is correct.
    state = _build_state("h12", ["8d", "7d"], ["Jd", "6d", "7c", "6s", "As"], [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 0, "action": "big_blind", "amount": 100},
        {"seat": 1, "action": "raise", "amount": 200},
        {"seat": 0, "action": "raise", "amount": 600},
        {"seat": 1, "action": "call", "amount": 400},
        {"seat": 0, "action": "raise", "amount": 600},
        {"seat": 1, "action": "call", "amount": 600},
        {"seat": 0, "action": "raise", "amount": 1200},
        {"seat": 1, "action": "call", "amount": 1200},
        {"seat": 0, "action": "raise", "amount": 7600}
    ], pot=4800, owed=7600, current_bet=7600, can_check=False, stack=7600, seat=1)
    
    bot = _load_bot("bots/skantbot7.4/bot.py")
    decision = bot.decide(state)
    assert decision.get("action") == "fold", f"Expected fold on h12, got {decision}"

def test_hand_18():
    # Bot opens 200, Pav 3-bets 600. Bot calls 55.
    # Flop [Ad Td 7c]. Pav bets 600, Bot folds.
    # Expected: Fold is correct.
    state = _build_state("h18", ["5s", "5c"], ["Ad", "Td", "7c"], [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 0, "action": "big_blind", "amount": 100},
        {"seat": 1, "action": "raise", "amount": 200},
        {"seat": 0, "action": "raise", "amount": 600},
        {"seat": 1, "action": "call", "amount": 400},
        {"seat": 0, "action": "raise", "amount": 600}
    ], pot=1200, owed=600, current_bet=600, can_check=False, stack=9400, seat=1)
    
    bot = _load_bot("bots/skantbot7.4/bot.py")
    decision = bot.decide(state)
    assert decision.get("action") == "fold", f"Expected fold on h18, got {decision}"

def test_hand_20():
    # Bot opens 200, Pav 3-bets 600. Bot calls 76s.
    # Flop [2s Js Qs]. Pav bets 600, Bot calls (flush draw).
    # Turn [3c]. Pav bets 1200, Bot calls.
    # River [8s]. Pav shoves 7600. Bot folds. (Hit the flush).
    # Wait, the bot has 7s 6s. It hits the flush. Why did it fold?
    # This might be Leak 2 (uncapped pot odds). Let's see what it does.
    # The true bug is uncapped owed. Since Stage 3 is DEFERRED, it will fold. We must assert fold to lock in current behavior.
    state = _build_state("h20", ["7s", "6s"], ["2s", "Js", "Qs", "3c", "8s"], [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 0, "action": "big_blind", "amount": 100},
        {"seat": 1, "action": "raise", "amount": 200},
        {"seat": 0, "action": "raise", "amount": 600},
        {"seat": 1, "action": "call", "amount": 400},
        {"seat": 0, "action": "raise", "amount": 600},
        {"seat": 1, "action": "call", "amount": 600},
        {"seat": 0, "action": "raise", "amount": 1200},
        {"seat": 1, "action": "call", "amount": 1200},
        {"seat": 0, "action": "raise", "amount": 7600}
    ], pot=4800, owed=7600, current_bet=7600, can_check=False, stack=7600, seat=1)
    
    bot = _load_bot("bots/skantbot7.4/bot.py")
    decision = bot.decide(state)
    assert decision.get("action") == "fold", f"Expected fold on h20 (due to deferred Leak 2), got {decision}"

def test_hand_25():
    # Pav opens 200. Bot calls J9o.
    # Flop [4c 7d 8c]. Pav bets 200, Bot calls.
    # Turn [5s]. Pav shoves 9600. Bot folds. (Gutshot + J high).
    # Expected: Fold is correct.
    state = _build_state("h25", ["Js", "9c"], ["4c", "7d", "8c", "5s"], [
        {"seat": 0, "action": "small_blind", "amount": 50},
        {"seat": 1, "action": "big_blind", "amount": 100},
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "call", "amount": 100},
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "call", "amount": 200},
        {"seat": 0, "action": "raise", "amount": 9600}
    ], pot=800, owed=9600, current_bet=9600, can_check=False, stack=9600, seat=1)
    
    bot = _load_bot("bots/skantbot7.4/bot.py")
    decision = bot.decide(state)
    assert decision.get("action") == "fold", f"Expected fold on h25, got {decision}"

def test_hand_32():
    # Bot opens 200. Pav 3-bets 600. Bot calls 87s.
    # Flop [2s Js Qs]. Pav bets 600, Bot folds.
    # Expected: Fold is correct.
    state = _build_state("h32", ["8d", "7d"], ["2s", "Js", "Qs"], [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 0, "action": "big_blind", "amount": 100},
        {"seat": 1, "action": "raise", "amount": 200},
        {"seat": 0, "action": "raise", "amount": 600},
        {"seat": 1, "action": "call", "amount": 400},
        {"seat": 0, "action": "raise", "amount": 600}
    ], pot=1200, owed=600, current_bet=600, can_check=False, stack=9400, seat=1)
    
    bot = _load_bot("bots/skantbot7.4/bot.py")
    decision = bot.decide(state)
    assert decision.get("action") == "fold", f"Expected fold on h32, got {decision}"

def test_hand_38():
    # We already have this in test_hand_38_leak.py, but include it here for completeness.
    # It must fold.
    state = _build_state("h38", ["Ad", "8d"], ["Qd", "7d", "3c", "8c"], [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 0, "action": "big_blind", "amount": 100},
        {"seat": 1, "action": "raise", "amount": 200},
        {"seat": 0, "action": "raise", "amount": 600},
        {"seat": 1, "action": "call", "amount": 400},
        {"seat": 1, "action": "check", "amount": 0},
        {"seat": 0, "action": "check", "amount": 0},
        {"seat": 1, "action": "check", "amount": 0},
        {"seat": 0, "action": "raise", "amount": 1500}
    ], pot=600, owed=1500, current_bet=1500, can_check=False, stack=8500, seat=1)
    
    bot = _load_bot("bots/skantbot7.4/bot.py")
    decision = bot.decide(state)
    assert decision.get("action") == "fold", f"Expected fold on h38, got {decision}"

def test_hand_30():
    # We opened, Pav called. Flop [Ac Qh Td]. We bet, Pav calls.
    # Turn [3c]. We bet, Pav calls.
    # River [2s]. We check, Pav shoves. Bot folds.
    state = _build_state("h30", ["Jc", "Jd"], ["Ac", "Qh", "Td", "3c", "2s"], [
        {"seat": 1, "action": "small_blind", "amount": 50},
        {"seat": 0, "action": "big_blind", "amount": 100},
        {"seat": 1, "action": "raise", "amount": 200},
        {"seat": 0, "action": "call", "amount": 100},
        {"seat": 1, "action": "raise", "amount": 200},
        {"seat": 0, "action": "call", "amount": 200},
        {"seat": 1, "action": "raise", "amount": 400},
        {"seat": 0, "action": "call", "amount": 400},
        {"seat": 1, "action": "check", "amount": 0},
        {"seat": 0, "action": "raise", "amount": 9200}
    ], pot=1600, owed=9200, current_bet=9200, can_check=False, stack=9200, seat=1)
    
    bot = _load_bot("bots/skantbot7.4/bot.py")
    decision = bot.decide(state)
    assert decision.get("action") == "fold", f"Expected fold on h30, got {decision}"

def test_hand_36():
    # Pav opens. Bot 3-bets A5s. Pav calls.
    # Flop [Kc 8h 2s]. Bot checks, Pav bets. Bot calls.
    # Turn [9d]. Bot checks, Pav shoves. Bot folds (A high).
    # Expected: Fold is correct.
    state = _build_state("h36", ["As", "5s"], ["Kc", "8h", "2s", "9d"], [
        {"seat": 0, "action": "small_blind", "amount": 50},
        {"seat": 1, "action": "big_blind", "amount": 100},
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "raise", "amount": 600},
        {"seat": 0, "action": "call", "amount": 400},
        {"seat": 1, "action": "check", "amount": 0},
        {"seat": 0, "action": "raise", "amount": 600},
        {"seat": 1, "action": "call", "amount": 600},
        {"seat": 1, "action": "check", "amount": 0},
        {"seat": 0, "action": "raise", "amount": 8800}
    ], pot=2400, owed=8800, current_bet=8800, can_check=False, stack=8800, seat=1)
    
    bot = _load_bot("bots/skantbot7.4/bot.py")
    decision = bot.decide(state)
    assert decision.get("action") == "fold", f"Expected fold on h36, got {decision}"


if __name__ == "__main__":
    for fn in (test_hand_02, test_hand_07, test_hand_12, test_hand_18, test_hand_20, test_hand_25, test_hand_32, test_hand_38, test_hand_30, test_hand_36):
        print(f"\\n===== {fn.__name__} =====")
        try:
            fn()
            print("PASS")
        except AssertionError as e:
            print(f"FAIL: {e}")

