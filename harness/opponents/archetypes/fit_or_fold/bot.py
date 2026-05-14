BOT_NAME = "FitOrFold"

def decide(state: dict) -> dict:
    phase = state["street"]
    if phase == "preflop":
        return {"action": "call"}
    
    hand = state["hole_cards"]
    board = [c[0] for c in state["board_cards"]]
    hit = hand[0][0] in board or hand[1][0] in board or hand[0][0] == hand[1][0]
    if hit:
        if state["can_raise"]: return {"action": "raise", "amount": min(state["max_raise"], state["pot"])}
        return {"action": "call"}
    
    if state["can_check"]: return {"action": "check"}
    return {"action": "fold"}
