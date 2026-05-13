"""Min Raiser: always raises to the minimum legal amount when possible."""

BOT_NAME = "MinRaiser"


def decide(state: dict) -> dict:
    if state.get("type") == "hand_complete":
        return {"action": "check"}
    stack = state.get("your_stack", 0)
    already_bet = state.get("your_bet_this_street", 0)
    min_raise = state.get("min_raise_to", 0)
    owed = state.get("amount_owed", 0)

    # Raise if we can afford the min-raise
    chips_to_raise = min_raise - already_bet
    if chips_to_raise > 0 and chips_to_raise < stack:
        return {"action": "raise", "amount": min_raise}

    # Can't raise: check or call if cheap enough, else fold
    if owed == 0:
        return {"action": "check"}
    if owed <= stack * 0.20:
        return {"action": "call"}
    return {"action": "fold"}
