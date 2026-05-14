BOT_NAME = "LoosePassive"

def decide(state: dict) -> dict:
    phase = state["street"]
    if phase == "preflop":
        if state["call_amount"] <= state["big_blind"] * 5:
            return {"action": "call"}
        if state["can_check"]: return {"action": "check"}
        return {"action": "fold"}
    
    if state["can_check"]: return {"action": "check"}
    return {"action": "call"}
