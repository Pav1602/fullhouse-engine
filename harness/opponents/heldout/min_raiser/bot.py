"""Min Raiser: always raises to the minimum legal amount when possible."""

BOT_NAME = "MinRaiser"


def decide(state: dict) -> dict:
    stack = state["your_stack"]
    already_bet = state["your_bet_this_street"]
    min_raise = state["min_raise_to"]
    owed = state["amount_owed"]

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
