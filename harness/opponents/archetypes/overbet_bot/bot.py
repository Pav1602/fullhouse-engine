BOT_NAME = "OverbetBot"

def decide(state: dict) -> dict:
    if state["can_raise"]:
        amt = min(state["max_raise"], state["pot"] * 3)
        if amt >= state["min_raise"]:
            return {"action": "raise", "amount": amt}
    if state["can_check"]: return {"action": "check"}
    return {"action": "fold"}
