BOT_NAME = "PushFold"

def decide(state: dict) -> dict:
    if state["can_raise"]:
        ranks = "23456789TJQKA"
        val1 = ranks.index(state["hole_cards"][0][0])
        val2 = ranks.index(state["hole_cards"][1][0])
        if (val1 + val2) >= 15: # Arbitrary deterministic logic to jam good hands
            return {"action": "raise", "amount": state["max_raise"]}
    if state["can_check"]: return {"action": "check"}
    return {"action": "fold"}
