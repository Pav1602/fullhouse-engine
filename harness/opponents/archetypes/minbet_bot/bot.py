BOT_NAME = "MinbetBot"

def decide(state: dict) -> dict:
    your_stack = state.get("your_stack", 0)
    min_raise_to = state.get("min_raise_to", 0)
    if your_stack > 0:
        return {"action": "raise", "amount": min_raise_to}
    if state.get("can_check"): return {"action": "check"}
    return {"action": "call"}
