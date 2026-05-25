BOT_NAME = "FitOrFold"

def decide(state: dict) -> dict:
    phase = state.get("street", "")
    if phase == "preflop":
        return {"action": "call"}

    hand = state.get("your_cards", [])
    if len(hand) != 2:
        if state.get("can_check"): return {"action": "check"}
        return {"action": "fold"}
    board = [c[0] for c in state.get("community_cards", [])]
    hit = hand[0][0] in board or hand[1][0] in board or hand[0][0] == hand[1][0]
    your_stack = state.get("your_stack", 0)
    your_bet   = state.get("your_bet_this_street", 0)
    pot        = state.get("pot", 0)
    if hit:
        if your_stack > 0:
            max_raise_to = your_bet + your_stack
            return {"action": "raise", "amount": min(max_raise_to, pot)}
        return {"action": "call"}

    if state.get("can_check"): return {"action": "check"}
    return {"action": "fold"}
