BOT_NAME = "OverbetBot"

def decide(state: dict) -> dict:
    your_stack = state.get("your_stack", 0)
    your_bet   = state.get("your_bet_this_street", 0)
    min_raise_to = state.get("min_raise_to", 0)
    max_raise_to = your_bet + your_stack
    pot = state.get("pot", 0)
    if your_stack > 0:
        amt = min(max_raise_to, pot * 3)
        if amt >= min_raise_to:
            return {"action": "raise", "amount": amt}
    if state.get("can_check"): return {"action": "check"}
    return {"action": "fold"}
