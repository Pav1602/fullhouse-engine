BOT_NAME = "DonkBot"

def decide(state: dict) -> dict:
    phase = state.get("street", "")
    your_stack = state.get("your_stack", 0)
    your_bet   = state.get("your_bet_this_street", 0)
    pot        = state.get("pot", 0)
    if phase != "preflop":
        if your_stack > 0:
            max_raise_to = your_bet + your_stack
            return {"action": "raise", "amount": min(max_raise_to, int(pot * 0.5))}
    if state.get("can_check"): return {"action": "check"}
    return {"action": "call"}
