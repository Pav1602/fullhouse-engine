"""Bot A: The Aggressor — raises constantly, bets big."""

import random
import os

_HAND_RNG = random.Random()

def get_hand_rng(state: dict) -> random.Random:
    hand_id = state.get('hand_id', '')
    seat = state.get('seat_to_act', 0)
    match_id = os.environ.get('SKANT_MATCH_ID', '')
    seed_str = f'{match_id}:{hand_id}:{seat}'
    return random.Random(hash(seed_str) & 0xFFFFFFFF)


BOT_NAME = "The Aggressor"

def get_hand_rng(state: dict) -> random.Random:
    hand_id = state.get("hand_id", "")
    seat = state.get("seat_to_act", 0)
    seed_str = f"{hand_id}:{seat}"
    return random.Random(hash(seed_str) & 0xFFFFFFFF)

def decide(state):
    global _HAND_RNG
    _HAND_RNG = get_hand_rng(state)

    rng = get_hand_rng(state)
    stack = state["your_stack"]
    pot   = state["pot"]
    min_r = state["min_raise_to"]

    if rng.random() < 0.7:
        raise_to = min(min_r * rng.randint(2, 4), stack + state["your_bet_this_street"])
        raise_to = max(raise_to, min_r)
        return {"action": "raise", "amount": raise_to}

    if state["can_check"]:
        return {"action": "check"}

    return {"action": "call"}
