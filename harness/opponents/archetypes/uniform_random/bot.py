"""Uniform Random: picks uniformly from all legal actions each decision."""


import random
import os

_HAND_RNG = random.Random()

def get_hand_rng(state: dict) -> random.Random:
    hand_id = state.get('hand_id', '')
    seat = state.get('seat_to_act', 0)
    match_id = os.environ.get('SKANT_MATCH_ID', '')
    seed_str = f'{match_id}:{hand_id}:{seat}'
    return random.Random(hash(seed_str) & 0xFFFFFFFF)


BOT_NAME = "UniformRandom"

def get_hand_rng(state: dict) -> random.Random:
    hand_id = state.get("hand_id", "")
    seat = state.get("seat_to_act", 0)
    seed_str = f"{hand_id}:{seat}"
    return random.Random(hash(seed_str) & 0xFFFFFFFF)

def decide(state: dict) -> dict:
    global _HAND_RNG
    _HAND_RNG = get_hand_rng(state)

    rng = get_hand_rng(state)
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

    choice = rng.choice(actions)
    if choice == "raise":
        # Random sizing between min_raise and 2× min_raise (capped to stack)
        max_raise = min(min_raise * 2, already_bet + stack)
        amount = rng.randint(min_raise, max(min_raise, max_raise))
        return {"action": "raise", "amount": amount}
    return {"action": choice}
