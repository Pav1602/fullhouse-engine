BOT_NAME = "CBetPunisher"

def decide(state: dict) -> dict:
    street = state.get("street", "")
    amount_owed = state.get("amount_owed", 0)
    your_stack = state.get("your_stack", 0)
    can_check = state.get("can_check", False)

    if street == "preflop":
        if amount_owed == 0:
            return {"action": "check"}
        elif amount_owed <= your_stack * 0.15:
            return {"action": "call"}
    elif street in ("flop", "turn", "river"):
        if amount_owed > 0:
            return {"action": "all_in"}
        else:
            return {"action": "check"}

    return {"action": "check"} if can_check else {"action": "fold"}
