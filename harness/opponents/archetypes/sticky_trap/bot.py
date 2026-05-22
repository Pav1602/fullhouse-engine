BOT_NAME = "StickyTrap"

def decide(state: dict) -> dict:
    street = state.get("street", "")
    amount_owed = state.get("amount_owed", 0)
    can_check = state.get("can_check", False)

    if street in ("preflop", "flop", "turn"):
        if amount_owed > 0:
            return {"action": "call"}
        else:
            return {"action": "check"}
    elif street == "river":
        return {"action": "all_in"}

    return {"action": "check"} if can_check else {"action": "fold"}
