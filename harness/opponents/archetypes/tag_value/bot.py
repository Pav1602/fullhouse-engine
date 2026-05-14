BOT_NAME = "TagValue"

def decide(state: dict) -> dict:
    hand = state["hole_cards"]
    phase = state["street"]
    ranks = "23456789TJQKA"
    val1 = ranks.index(hand[0][0])
    val2 = ranks.index(hand[1][0])
    is_pair = hand[0][0] == hand[1][0]
    
    if phase == "preflop":
        if is_pair and val1 >= 8: # TT+
            if state["can_raise"]:
                return {"action": "raise", "amount": min(state["max_raise"], state["pot"] * 2)}
            return {"action": "call"}
        if (val1 >= 10 and val2 >= 10) or (val1 >= 12 or val2 >= 12): # Broadways or A
            return {"action": "call"}
        if state["can_check"]: return {"action": "check"}
        return {"action": "fold"}
    else:
        board = [c[0] for c in state["board_cards"]]
        hit = hand[0][0] in board or hand[1][0] in board or is_pair
        if hit:
            if state["can_raise"]:
                return {"action": "raise", "amount": min(state["max_raise"], state["pot"])}
            return {"action": "call"}
        else:
            if state["can_check"]: return {"action": "check"}
            return {"action": "fold"}
