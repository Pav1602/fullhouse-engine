BOT_NAME = "ManiacAggro"

def decide(state: dict) -> dict:
    if state["can_raise"]:
        return {"action": "raise", "amount": min(state["max_raise"], state["pot"])}
    if state["can_check"]: return {"action": "check"}
    return {"action": "call"}
