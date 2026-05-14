BOT_NAME = "DonkBot"

def decide(state: dict) -> dict:
    phase = state["street"]
    if phase != "preflop":
        if state["can_raise"]:
            return {"action": "raise", "amount": min(state["max_raise"], int(state["pot"] * 0.5))}
    if state["can_check"]: return {"action": "check"}
    return {"action": "call"}
