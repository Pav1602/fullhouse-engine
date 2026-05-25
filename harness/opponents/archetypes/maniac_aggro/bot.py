BOT_NAME = "ManiacAggro"

def decide(state: dict) -> dict:
    your_stack = state.get("your_stack", 0)
    your_bet   = state.get("your_bet_this_street", 0)
    pot        = state.get("pot", 0)
    if your_stack > 0:
        max_raise_to = your_bet + your_stack
        return {"action": "raise", "amount": min(max_raise_to, pot)}
    if state.get("can_check"): return {"action": "check"}
    return {"action": "call"}
