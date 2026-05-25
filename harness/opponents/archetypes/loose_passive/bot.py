BOT_NAME = "LoosePassive"

BB = 100

def decide(state: dict) -> dict:
    phase = state.get("street", "")
    owed = state.get("amount_owed", 0)
    if phase == "preflop":
        if owed <= BB * 5:
            return {"action": "call"}
        if state.get("can_check"): return {"action": "check"}
        return {"action": "fold"}

    if state.get("can_check"): return {"action": "check"}
    return {"action": "call"}
