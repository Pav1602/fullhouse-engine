"""Super Nit: only plays AA or KK preflop (jams), folds/checks everything else."""

BOT_NAME = "SuperNit"

_MONSTERS = {("A", "A"), ("K", "K")}


def decide(state: dict) -> dict:
    street = state["street"]

    if street == "preflop":
        ranks = tuple(sorted([c[0] for c in state["your_cards"]], reverse=True))
        if ranks in _MONSTERS:
            return {"action": "all_in"}
        if state["can_check"]:
            return {"action": "check"}
        return {"action": "fold"}

    # Postflop: always check, fold to any bet
    if state["can_check"]:
        return {"action": "check"}
    return {"action": "fold"}
