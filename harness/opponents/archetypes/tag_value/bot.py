BOT_NAME = "TagValue"

def decide(state: dict) -> dict:
    hand = state.get("your_cards", [])
    if len(hand) != 2:
        if state.get("can_check"): return {"action": "check"}
        return {"action": "fold"}
    phase = state.get("street", "")
    your_stack = state.get("your_stack", 0)
    your_bet   = state.get("your_bet_this_street", 0)
    pot        = state.get("pot", 0)
    max_raise_to = your_bet + your_stack
    ranks = "23456789TJQKA"
    val1 = ranks.index(hand[0][0])
    val2 = ranks.index(hand[1][0])
    is_pair = hand[0][0] == hand[1][0]

    if phase == "preflop":
        if is_pair and val1 >= 8: # TT+
            if your_stack > 0:
                return {"action": "raise", "amount": min(max_raise_to, pot * 2)}
            return {"action": "call"}
        if (val1 >= 10 and val2 >= 10) or (val1 >= 12 or val2 >= 12): # Broadways or A
            return {"action": "call"}
        if state.get("can_check"): return {"action": "check"}
        return {"action": "fold"}
    else:
        board = [c[0] for c in state.get("community_cards", [])]
        hit = hand[0][0] in board or hand[1][0] in board or is_pair
        if hit:
            if your_stack > 0:
                return {"action": "raise", "amount": min(max_raise_to, pot)}
            return {"action": "call"}
        else:
            if state.get("can_check"): return {"action": "check"}
            return {"action": "fold"}
