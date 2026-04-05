"""
Python port of queue/tournament.js
Swiss pairing, standings computation, finalist selection.
Used by the demo server and the worker.
"""

import random


def swiss_pairing(standings, table_size=6):
    """
    Pair bots into tables. standings is a list of dicts with bot_id, bot_path,
    cumulative_delta. Returns list of tables (each table = list of bot dicts).
    """
    sorted_bots = sorted(standings, key=lambda b: -b.get("cumulative_delta", 0))

    tables = []
    i = 0
    while i < len(sorted_bots):
        remaining = len(sorted_bots) - i
        if remaining < table_size and tables:
            # fold stragglers into last table
            tables[-1].extend(sorted_bots[i:])
            break
        tables.append(sorted_bots[i:i + table_size])
        i += table_size

    return tables


def compute_standings(all_results):
    """
    all_results: list of {bot_id, bot_path, chip_delta}
    Returns sorted list of {bot_id, bot_path, cumulative_delta, matches_played}
    """
    totals = {}
    for r in all_results:
        bid = r["bot_id"]
        if bid not in totals:
            totals[bid] = {
                "bot_id": bid,
                "bot_path": r.get("bot_path", ""),
                "cumulative_delta": 0,
                "matches_played": 0,
            }
        totals[bid]["cumulative_delta"] += r["chip_delta"]
        totals[bid]["matches_played"] += 1

    return sorted(totals.values(), key=lambda b: -b["cumulative_delta"])


def select_finalists(standings, n=32):
    return standings[:n]
