"""Uniform Random: picks uniformly from all legal actions each decision."""

import random

BOT_NAME = "UniformRandom"


def decide(state: dict) -> dict:
    stack = state["your_stack"]
    already_bet = state["your_bet_this_street"]
    min_raise = state["min_raise_to"]
    owed = state["amount_owed"]

    actions = ["fold"]
    if state["can_check"]:
        actions.append("check")
    elif owed > 0:
        actions.append("call")

    # Add raise if we can afford the minimum
    chips_to_raise = min_raise - already_bet
    if chips_to_raise > 0 and chips_to_raise < stack:
        actions.append("raise")

    choice = random.choice(actions)
    if choice == "raise":
        # Random sizing between min_raise and 2× min_raise (capped to stack)
        max_raise = min(min_raise * 2, already_bet + stack)
        amount = random.randint(min_raise, max(min_raise, max_raise))
        return {"action": "raise", "amount": amount}
    return {"action": choice}
