"""Limp Machine: limps preflop (calls up to 3x BB), folds to big raises.
Postflop: calls when getting 2:1 pot odds or better, otherwise folds."""

BOT_NAME = "LimpMachine"

_THREE_BB = 300  # threshold: call any preflop raise ≤ 3x big blind


def decide(state: dict) -> dict:
    owed = state["amount_owed"]
    pot = state["pot"]

    if state["street"] == "preflop":
        if state["can_check"]:
            return {"action": "check"}
        if owed <= _THREE_BB:
            return {"action": "call"}
        return {"action": "fold"}

    # Postflop: pot odds ≥ 2:1 means call
    if state["can_check"]:
        return {"action": "check"}
    if owed > 0 and pot / owed >= 2.0:
        return {"action": "call"}
    return {"action": "fold"}
