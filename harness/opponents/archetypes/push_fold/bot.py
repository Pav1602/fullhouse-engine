BOT_NAME = "PushFold"

def decide(state: dict) -> dict:
    your_cards = state.get("your_cards", [])
    your_stack = state.get("your_stack", 0)
    your_bet   = state.get("your_bet_this_street", 0)
    if your_stack > 0 and len(your_cards) == 2:
        ranks = "23456789TJQKA"
        val1 = ranks.index(your_cards[0][0])
        val2 = ranks.index(your_cards[1][0])
        if (val1 + val2) >= 15: # Arbitrary deterministic logic to jam good hands
            return {"action": "raise", "amount": your_bet + your_stack}
    if state.get("can_check"): return {"action": "check"}
    return {"action": "fold"}
