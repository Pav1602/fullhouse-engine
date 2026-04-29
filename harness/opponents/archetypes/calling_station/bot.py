"""Calling Station: never folds, never raises — always calls or checks."""

BOT_NAME = "CallingStation"


def decide(state: dict) -> dict:
    if state["can_check"]:
        return {"action": "check"}
    return {"action": "call"}
