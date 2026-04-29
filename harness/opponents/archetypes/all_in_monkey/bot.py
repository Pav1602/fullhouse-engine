"""All-In Monkey: shoves all-in every single action."""

BOT_NAME = "AllInMonkey"


def decide(state: dict) -> dict:
    return {"action": "all_in"}
