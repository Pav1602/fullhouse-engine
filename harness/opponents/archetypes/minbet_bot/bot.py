BOT_NAME = "MinbetBot"

def decide(state: dict) -> dict:
    if state["can_raise"]:
        return {"action": "raise", "amount": state["min_raise"]}
    if state["can_check"]: return {"action": "check"}
    return {"action": "call"}
