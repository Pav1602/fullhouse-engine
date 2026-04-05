#!/usr/bin/env python3
"""
Fullhouse Hackathon — Setup Script
Run: python3 setup_fullhouse.py
Creates ~/Desktop/fullhouse with everything ready to go.
"""
import os, sys

BASE = os.path.expanduser("~/Desktop/fullhouse")

files = {}

# ── engine/game.py ────────────────────────────────────────────────────────────
files["engine/game.py"] = '''"""
Fullhouse Hackathon — No-Limit Texas Hold\'em Game Engine
6-max, using eval7 (same library as MIT Pokerbots production).
"""

import eval7
from dataclasses import dataclass, field
from typing import Optional

SMALL_BLIND    = 50
BIG_BLIND      = 100
STARTING_STACK = 10_000
MAX_PLAYERS    = 9

@dataclass
class Player:
    seat: int
    bot_id: str
    stack: int
    hole_cards: list = field(default_factory=list)
    is_folded: bool = False
    is_all_in: bool = False
    bet_this_street: int = 0

    @property
    def is_active(self):
        return not self.is_folded and not self.is_all_in

    def to_public_dict(self):
        return {
            "seat": self.seat, "bot_id": self.bot_id, "stack": self.stack,
            "is_folded": self.is_folded, "is_all_in": self.is_all_in,
            "bet_this_street": self.bet_this_street, "hole_cards": None,
        }

@dataclass
class Action:
    seat: int
    action: str
    amount: int = 0
    def to_dict(self):
        return {"seat": self.seat, "action": self.action, "amount": self.amount}

class PokerEngine:
    def __init__(self, hand_id, bot_ids, dealer_seat=0, starting_stacks=None):
        assert 2 <= len(bot_ids) <= MAX_PLAYERS
        stacks = starting_stacks or {}
        self.players = [
            Player(seat=i, bot_id=bid, stack=stacks.get(bid, STARTING_STACK))
            for i, bid in enumerate(bot_ids)
        ]
        self.n = len(self.players)
        self.dealer_seat = dealer_seat % self.n
        self.hand_id = hand_id
        self.pot = 0
        self.community_cards = []
        self.street = "preflop"
        self.action_log = []
        self.current_bet = 0
        self.min_raise = BIG_BLIND
        self._needs_to_act = set()
        self._deck = None

    def start_hand(self):
        self._post_blinds()
        self._deal_hole_cards()
        first = self._utg_seat()
        self._set_needs_to_act_except(self._bb_seat())
        return self._build_state(first)

    def apply_action(self, seat, raw):
        action = self._validate(seat, raw)
        self.action_log.append(action.to_dict())
        self._needs_to_act.discard(seat)
        p = self.players[seat]

        if action.action == "fold":
            p.is_folded = True
        elif action.action == "check":
            pass
        elif action.action == "call":
            owed = self.current_bet - p.bet_this_street
            self._put_in(seat, min(owed, p.stack))
            if p.stack == 0: p.is_all_in = True
        elif action.action == "raise":
            chips_needed = action.amount - p.bet_this_street
            prev_bet = self.current_bet
            self._put_in(seat, min(chips_needed, p.stack))
            self.min_raise = self.current_bet - prev_bet
            if p.stack == 0: p.is_all_in = True
            self._set_needs_to_act_except(seat)
        elif action.action == "all_in":
            prev_bet = self.current_bet
            self._put_in(seat, p.stack)
            if self.current_bet > prev_bet:
                self.min_raise = max(self.min_raise, self.current_bet - prev_bet)
                self._set_needs_to_act_except(seat)
            p.is_all_in = True

        remaining = [pl for pl in self.players if not pl.is_folded]
        if len(remaining) == 1:
            return self._award_uncontested(remaining[0])
        return self._advance_if_street_over(seat)

    def _advance_if_street_over(self, last_seat):
        next_seat = self._next_actor(last_seat)
        if next_seat is not None:
            return self._build_state(next_seat)
        return self._advance_street()

    def _advance_street(self):
        for p in self.players:
            p.bet_this_street = 0
        self.current_bet = 0
        self.min_raise = BIG_BLIND
        if self.street == "preflop":
            self.community_cards += self._deck.deal(3); self.street = "flop"
        elif self.street == "flop":
            self.community_cards += self._deck.deal(1); self.street = "turn"
        elif self.street == "turn":
            self.community_cards += self._deck.deal(1); self.street = "river"
        elif self.street == "river":
            return self._showdown()
        first = self._first_postflop_actor()
        if first is None: return self._run_it_out()
        self._set_needs_to_act_except(None)
        return self._build_state(first)

    def _run_it_out(self):
        while self.street != "river":
            if self.street == "flop":
                self.community_cards += self._deck.deal(1); self.street = "turn"
            elif self.street == "turn":
                self.community_cards += self._deck.deal(1); self.street = "river"
        return self._showdown()

    def _sb_seat(self): return (self.dealer_seat + 1) % self.n
    def _bb_seat(self): return (self.dealer_seat + 2) % self.n

    def _utg_seat(self):
        bb = self._bb_seat()
        for offset in range(1, self.n + 1):
            s = (bb + offset) % self.n
            if self.players[s].is_active: return s
        return bb

    def _next_actor(self, from_seat):
        if not self._needs_to_act: return None
        for offset in range(1, self.n + 1):
            seat = (from_seat + offset) % self.n
            if seat in self._needs_to_act and self.players[seat].is_active:
                return seat
        return None

    def _first_postflop_actor(self):
        for offset in range(1, self.n + 1):
            s = (self.dealer_seat + offset) % self.n
            if self.players[s].is_active: return s
        return None

    def _set_needs_to_act_except(self, exclude_seat):
        self._needs_to_act = {
            p.seat for p in self.players if p.is_active and p.seat != exclude_seat
        }

    def _post_blinds(self):
        sb, bb = self._sb_seat(), self._bb_seat()
        self._put_in(sb, min(SMALL_BLIND, self.players[sb].stack))
        self._put_in(bb, min(BIG_BLIND, self.players[bb].stack))
        self.current_bet = BIG_BLIND
        self.min_raise = BIG_BLIND
        self.action_log.append({"seat": sb, "action": "small_blind", "amount": SMALL_BLIND})
        self.action_log.append({"seat": bb, "action": "big_blind", "amount": BIG_BLIND})

    def _put_in(self, seat, amount):
        amount = max(0, min(amount, self.players[seat].stack))
        self.players[seat].stack -= amount
        self.players[seat].bet_this_street += amount
        self.pot += amount
        if self.players[seat].bet_this_street > self.current_bet:
            self.current_bet = self.players[seat].bet_this_street

    def _deal_hole_cards(self):
        self._deck = eval7.Deck()
        self._deck.shuffle()
        for p in self.players: p.hole_cards = self._deck.deal(2)

    def _validate(self, seat, raw):
        p = self.players[seat]
        act = str(raw.get("action", "fold")).lower().strip()
        amount = int(raw.get("amount", 0))
        if act not in ("fold","check","call","raise","all_in"):
            return Action(seat, "fold")
        owed = self.current_bet - p.bet_this_street
        if act == "check" and owed > 0: act = "call"
        if act == "raise":
            min_total = self.current_bet + self.min_raise
            amount = max(amount, min_total)
            if (amount - p.bet_this_street) >= p.stack:
                return Action(seat, "all_in", p.stack + p.bet_this_street)
            return Action(seat, "raise", amount)
        if act == "all_in": amount = p.stack + p.bet_this_street
        return Action(seat, act, amount)

    def _showdown(self):
        contenders = [p for p in self.players if not p.is_folded]
        if len(contenders) == 1: return self._award_uncontested(contenders[0])
        scored = [(eval7.evaluate(p.hole_cards + self.community_cards), p) for p in contenders]
        best = max(s for s, _ in scored)
        winners = [p for s, p in scored if s == best]
        split = self.pot // len(winners)
        remainder = self.pot % len(winners)
        results = []
        for i, w in enumerate(winners):
            award = split + (remainder if i == 0 else 0)
            w.stack += award
            results.append({"bot_id": w.bot_id, "seat": w.seat, "amount": award})
        revealed = {p.bot_id: [str(c) for c in p.hole_cards] for _, p in scored}
        return self._build_result(results, showdown=True, revealed=revealed)

    def _award_uncontested(self, winner):
        winner.stack += self.pot
        return self._build_result([{"bot_id": winner.bot_id, "seat": winner.seat, "amount": self.pot}], showdown=False)

    def _build_state(self, seat):
        p = self.players[seat]
        owed = max(0, self.current_bet - p.bet_this_street)
        return {
            "type": "action_request", "hand_id": self.hand_id, "street": self.street,
            "seat_to_act": seat, "pot": self.pot,
            "community_cards": [str(c) for c in self.community_cards],
            "current_bet": self.current_bet, "min_raise_to": self.current_bet + self.min_raise,
            "amount_owed": owed, "can_check": owed == 0,
            "your_cards": [str(c) for c in p.hole_cards], "your_stack": p.stack,
            "your_bet_this_street": p.bet_this_street,
            "players": [pl.to_public_dict() for pl in self.players],
            "action_log": list(self.action_log),
        }

    def _build_result(self, winners, showdown, revealed=None):
        return {
            "type": "hand_complete", "hand_id": self.hand_id, "street": self.street,
            "pot": self.pot, "community_cards": [str(c) for c in self.community_cards],
            "winners": winners, "showdown": showdown, "revealed_cards": revealed or {},
            "action_log": list(self.action_log),
            "final_stacks": {p.bot_id: p.stack for p in self.players},
        }
'''

# ── sandbox/runner.py ─────────────────────────────────────────────────────────
files["sandbox/runner.py"] = '''import sys, json, importlib.util, traceback, signal, os

BOT_PATH = os.environ.get("BOT_PATH", "/bot/bot.py")
TIMEOUT  = int(os.environ.get("ACTION_TIMEOUT", "2"))

def load_bot(path):
    spec = importlib.util.spec_from_file_location("bot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "decide"):
        raise AttributeError("bot.py must define a decide() function")
    return module

def _timeout(signum, frame): raise TimeoutError()
def emit(obj): print(json.dumps(obj), flush=True)

def main():
    try:
        bot = load_bot(BOT_PATH)
    except Exception as e:
        sys.stderr.write(f"[runner] LOAD ERROR: {e}\\n")
        for line in sys.stdin: emit({"action": "fold", "error": "load_failed"})
        return

    signal.signal(signal.SIGALRM, _timeout)
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try:
            state = json.loads(line)
        except json.JSONDecodeError as e:
            emit({"action": "fold", "error": "bad_json"}); continue

        signal.alarm(TIMEOUT)
        try:
            action = bot.decide(state)
            signal.alarm(0)
            if not isinstance(action, dict) or "action" not in action:
                raise ValueError("bad return")
            emit(action)
        except TimeoutError:
            signal.alarm(0)
            emit({"action": "fold", "error": "timeout"})
        except Exception:
            signal.alarm(0)
            sys.stderr.write(f"[runner] BOT EXCEPTION:\\n{traceback.format_exc()}\\n")
            emit({"action": "fold", "error": "exception"})

if __name__ == "__main__": main()
'''

# ── sandbox/match.py ──────────────────────────────────────────────────────────
files["sandbox/match.py"] = '''import json, subprocess, sys, os, time, uuid, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.game import PokerEngine, STARTING_STACK

RUNNER_PATH = Path(__file__).parent / "runner.py"
USE_DOCKER  = os.environ.get("USE_DOCKER", "false").lower() == "true"
ACTION_TIMEOUT = int(os.environ.get("ACTION_TIMEOUT", "2"))

class BotProcess:
    def __init__(self, bot_id, bot_path):
        self.bot_id = bot_id; self.bot_path = bot_path; self.errors = []
        self._proc = self._start()

    def _start(self):
        cmd = [sys.executable, "-u", str(RUNNER_PATH)]
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
            env={**os.environ, "BOT_PATH": self.bot_path, "ACTION_TIMEOUT": str(ACTION_TIMEOUT)})

    def act(self, game_state):
        try:
            self._proc.stdin.write(json.dumps(game_state) + "\\n")
            self._proc.stdin.flush()
            line = self._proc.stdout.readline()
            if not line: raise EOFError("Bot process died")
            action = json.loads(line.strip())
            if "error" in action: self.errors.append(action["error"])
            return action
        except Exception as e:
            self.errors.append(str(e))
            return {"action": "fold", "error": str(e)}

    def stderr_lines(self): return []

    def stop(self):
        try: self._proc.stdin.close()
        except: pass
        try: self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired: self._proc.kill()

def run_match(match_id, bot_paths, n_hands=200, verbose=False):
    bot_ids = list(bot_paths.keys())
    assert 2 <= len(bot_ids) <= 9
    procs   = {bid: BotProcess(bid, path) for bid, path in bot_paths.items()}
    stacks  = {bid: STARTING_STACK for bid in bot_ids}
    hand_log = []; dealer = 0; start_ts = time.time()
    try:
        for hand_num in range(n_hands):
            alive = [bid for bid in bot_ids if stacks[bid] > 0]
            if len(alive) < 2: break
            hand_id = f"{match_id}_h{hand_num:04d}"
            engine  = PokerEngine(hand_id, alive, dealer_seat=dealer % len(alive),
                                  starting_stacks={bid: stacks[bid] for bid in alive})
            state = engine.start_hand(); steps = 0
            while state.get("type") == "action_request":
                seat = state["seat_to_act"]; bot_id = alive[seat]
                action = procs[bot_id].act(state)
                state = engine.apply_action(seat, action); steps += 1
                if steps > 1000: raise RuntimeError("Hand exceeded 1000 steps")
            hand_log.append({"hand_num": hand_num, "hand_id": hand_id, **state})
            for bid, s in state["final_stacks"].items(): stacks[bid] = s
            dealer += 1
    finally:
        for p in procs.values(): p.stop()
    return {
        "match_id": match_id, "bot_ids": bot_ids, "n_hands": len(hand_log),
        "duration_s": round(time.time() - start_ts, 2),
        "final_stacks": stacks,
        "chip_delta": {bid: stacks[bid] - STARTING_STACK for bid in bot_ids},
        "bot_errors": {bid: procs[bid].errors for bid in bot_ids},
        "hands": hand_log,
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bots", nargs="+")
    parser.add_argument("--hands", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--match-id", default=None)
    args = parser.parse_args()
    paths = {}
    for i, path in enumerate(args.bots):
        bot_id = Path(path).parent.name or f"bot_{i}"
        paths[bot_id] = path
    match_id = args.match_id or os.environ.get("MATCH_ID") or f"local_{uuid.uuid4().hex[:8]}"
    if not args.json: print(f"Starting match {match_id} with {len(paths)} bots, {args.hands} hands\\n")
    result = run_match(match_id, paths, n_hands=args.hands)
    if args.json:
        print(json.dumps({"match_id": result["match_id"], "n_hands": result["n_hands"],
            "duration_s": result["duration_s"], "final_stacks": result["final_stacks"],
            "chip_delta": result["chip_delta"], "bot_errors": result["bot_errors"]}))
        sys.exit(0)
    print(f"\\n{\'=\'*50}\\nMatch complete in {result[\'duration_s\']}s\\n{\'=\'*50}")
    print(f"{\'Bot\':<25} {\'Final Stack\':>12} {\'Delta\':>10}\\n{\'-\'*50}")
    for bid in sorted(result["bot_ids"], key=lambda b: -result["final_stacks"][b]):
        delta = result["chip_delta"][bid]; sign = "+" if delta >= 0 else ""
        print(f"{bid:<25} {result[\'final_stacks\'][bid]:>12,} {sign}{delta:>9,}")
    print(f"\\nHands played: {result[\'n_hands\']}")
'''

# ── matchqueue/tournament.py ──────────────────────────────────────────────────
files["matchqueue/tournament.py"] = '''def swiss_pairing(standings, table_size=6):
    sorted_bots = sorted(standings, key=lambda b: -b.get("cumulative_delta", 0))
    tables = []; i = 0
    while i < len(sorted_bots):
        remaining = len(sorted_bots) - i
        if remaining < table_size and tables:
            tables[-1].extend(sorted_bots[i:]); break
        tables.append(sorted_bots[i:i + table_size]); i += table_size
    return tables

def compute_standings(all_results):
    totals = {}
    for r in all_results:
        bid = r["bot_id"]
        if bid not in totals:
            totals[bid] = {"bot_id": bid, "bot_path": r.get("bot_path",""),
                           "cumulative_delta": 0, "matches_played": 0}
        totals[bid]["cumulative_delta"] += r["chip_delta"]
        totals[bid]["matches_played"] += 1
    return sorted(totals.values(), key=lambda b: -b["cumulative_delta"])

def select_finalists(standings, n=32):
    return standings[:n]
'''

# ── bots ──────────────────────────────────────────────────────────────────────
files["bots/template/bot.py"] = '''"""Your bot — edit the decide() function."""
import random

BOT_NAME = "My Bot"

def decide(game_state):
    my_cards = game_state["your_cards"]
    amount_owed = game_state["amount_owed"]
    pot = game_state["pot"]
    ranks = [c[0] for c in my_cards]
    if ranks.count("A") == 2 or ranks.count("K") == 2:
        raise_to = max(pot * 3, game_state["min_raise_to"])
        return {"action": "raise", "amount": int(raise_to)}
    if game_state["can_check"]:
        return {"action": "check"}
    if amount_owed < pot * 0.25:
        return {"action": "call"}
    return {"action": "fold"}
'''

files["bots/aggressor/bot.py"] = '''"""The Aggressor — raises constantly."""
import random
BOT_NAME = "The Aggressor"
def decide(state):
    min_r = state["min_raise_to"]
    stack = state["your_stack"]
    if random.random() < 0.7:
        raise_to = min(min_r * random.randint(2,4), stack + state["your_bet_this_street"])
        return {"action": "raise", "amount": max(int(raise_to), min_r)}
    if state["can_check"]: return {"action": "check"}
    return {"action": "call"}
'''

files["bots/mathematician/bot.py"] = '''"""The Mathematician — pure pot odds."""
BOT_NAME = "The Mathematician"
def decide(state):
    owed = state["amount_owed"]; pot = state["pot"]
    if state["can_check"]: return {"action": "check"}
    if owed == 0: return {"action": "check"}
    if pot / owed >= 3.0: return {"action": "call"}
    return {"action": "fold"}
'''

files["bots/shark/bot.py"] = '''"""The Shark — tight preflop, position-aware."""
import random
BOT_NAME = "The Shark"
STRONG = {("A","A"),("K","K"),("Q","Q"),("J","J"),("T","T"),("A","K"),("A","Q"),("A","J"),("K","Q")}
def hand_strength(cards):
    ranks = tuple(sorted([c[0] for c in cards], reverse=True))
    suited = cards[0][1] == cards[1][1]
    if ranks in STRONG: return "strong"
    if ranks[0] in "AKQJT" or suited: return "medium"
    return "weak"
def decide(state):
    street = state["street"]; owed = state["amount_owed"]; pot = state["pot"]
    n = len(state["players"]); seat = state["seat_to_act"]
    position = seat / max(n-1, 1)
    if street == "preflop":
        s = hand_strength(state["your_cards"])
        if s == "strong":
            rt = max(state["min_raise_to"] * 3, state["min_raise_to"])
            return {"action": "raise", "amount": int(rt)}
        if s == "medium" and position > 0.5 and owed < pot * 0.2:
            return {"action": "call"}
        if state["can_check"]: return {"action": "check"}
        return {"action": "fold"}
    if state["can_check"]:
        if position > 0.6 and random.random() < 0.4:
            bet = max(int(pot * 0.6), state["min_raise_to"])
            return {"action": "raise", "amount": bet}
        return {"action": "check"}
    threshold = 0.25 if position > 0.5 else 0.15
    if pot > 0 and owed / pot <= threshold: return {"action": "call"}
    return {"action": "fold"}
'''

files["bots/ref_bot_2/bot.py"] = '''"""Pot-odds caller."""
BOT_NAME = "Pot-Odds Bot"
def decide(state):
    owed = state["amount_owed"]; pot = state["pot"]
    if state["can_check"]: return {"action": "check"}
    if owed == 0 or pot / owed >= 3: return {"action": "call"}
    return {"action": "fold"}
'''

# ── demo.py ───────────────────────────────────────────────────────────────────
files["demo.py"] = r'''"""
Fullhouse Hackathon — Local Demo
Run: python3 demo.py
Open: http://localhost:5000
"""
import sys, os, json, time, threading, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, Response, jsonify, render_template_string
from sandbox.match import run_match
from matchqueue.tournament import swiss_pairing, compute_standings, select_finalists

app = Flask(__name__)

BOT_PATHS = {
    "The Aggressor":     "bots/aggressor/bot.py",
    "The Mathematician": "bots/mathematician/bot.py",
    "The Shark":         "bots/shark/bot.py",
    "Template Bot A":    "bots/template/bot.py",
    "Pot-Odds Bot":      "bots/ref_bot_2/bot.py",
    "Template Bot B":    "bots/template/bot.py",
}

state = {"log": [], "standings": [], "hands": [], "running": False}
log_lock = threading.Lock()

def emit(msg, kind="info"):
    with log_lock:
        state["log"].append({"t": time.time(), "msg": msg, "kind": kind})

PAGE = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Fullhouse Demo</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#080c08;color:#00ff41;font-family:'Courier New',monospace;font-size:14px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;height:100vh;background:#1a2e1a}
.panel{background:#080c08;padding:16px;overflow:hidden;display:flex;flex-direction:column}
.header{grid-column:1/-1;border-bottom:1px solid #00ff41;padding:12px 16px;display:flex;align-items:center;gap:24px;background:#080c08}
.logo{font-size:18px;letter-spacing:2px}
.blink{animation:blink 1s step-end infinite}
@keyframes blink{50%{opacity:0}}
h2{font-size:11px;letter-spacing:3px;color:#00cc33;margin-bottom:12px;text-transform:uppercase}
#log{flex:1;overflow-y:auto;font-size:12px;line-height:1.8}
#log div{padding:1px 0}
.info{color:#00ff41}.win{color:#00ffcc}.err{color:#ff4444}.dim{color:#3a6e3a}.bold{color:#fff}
#board{flex:1;overflow-y:auto}
.row{display:grid;grid-template-columns:28px 1fr 90px 70px;gap:8px;padding:5px 0;border-bottom:1px solid #0d1f0d;font-size:13px}
.row.hdr{color:#3a6e3a;font-size:11px;letter-spacing:1px}
.pos{color:#00ffcc}.neg{color:#ff4444}
.bar-wrap{background:#0d1f0d;height:4px;border-radius:2px;margin-top:2px}
.bar{height:4px;background:#00ff41;border-radius:2px;transition:width .5s}
.controls{margin-top:12px;display:flex;gap:10px;flex-wrap:wrap}
button{background:transparent;border:1px solid #00ff41;color:#00ff41;font-family:inherit;font-size:12px;padding:6px 16px;cursor:pointer;letter-spacing:1px;transition:all .15s}
button:hover{background:#00ff41;color:#080c08}
button:disabled{opacity:.3;cursor:not-allowed}
button:disabled:hover{background:transparent;color:#00ff41}
.pill{font-size:11px;letter-spacing:2px;padding:3px 10px;border:1px solid #3a6e3a;color:#3a6e3a}
.pill.running{border-color:#00ff41;color:#00ff41;animation:pulse 1s ease-in-out infinite}
@keyframes pulse{50%{opacity:.5}}
#replay{flex:1;overflow-y:auto;font-size:12px}
.hcard{border:1px solid #1a2e1a;padding:8px 10px;margin-bottom:6px}
.hcard:hover{border-color:#3a6e3a}
.hmeta{color:#3a6e3a;font-size:11px;margin-bottom:4px}
.aline{color:#00cc33}.aline.fold{color:#3a6e3a}.aline.raise{color:#00ffcc}
.community{color:#fff;letter-spacing:2px}
</style></head><body>
<div class="grid">
  <div class="header">
    <span class="logo">FULLHOUSE<span class="blink">_</span></span>
    <span class="pill" id="status">IDLE</span>
    <span style="color:#3a6e3a;font-size:11px" id="rlabel"></span>
  </div>
  <div class="panel">
    <h2>Event log</h2>
    <div id="log"></div>
    <div class="controls">
      <button id="b1" onclick="runSingle()">Run 1 match</button>
      <button id="b2" onclick="runTournament()">Run full tournament</button>
      <button onclick="document.getElementById('log').innerHTML=''">Clear</button>
    </div>
  </div>
  <div class="panel">
    <h2>Leaderboard</h2>
    <div id="board"><div class="row hdr"><span>#</span><span>Bot</span><span>Chip delta</span><span>Matches</span></div></div>
  </div>
  <div class="panel" style="grid-column:1/-1;max-height:240px">
    <h2>Last match — hand replay <span id="hcount" style="color:#3a6e3a"></span></h2>
    <div id="replay"></div>
  </div>
</div>
<script>
let running=false;
const es=new EventSource('/stream');
es.onmessage=e=>{const{msg,kind}=JSON.parse(e.data);addLog(msg,kind)};
function addLog(msg,kind='info'){const el=document.getElementById('log');const d=document.createElement('div');d.className=kind;d.textContent='> '+msg;el.appendChild(d);el.scrollTop=el.scrollHeight}
function setRunning(v){running=v;document.getElementById('b1').disabled=v;document.getElementById('b2').disabled=v;const p=document.getElementById('status');p.textContent=v?'RUNNING':'IDLE';p.className='pill'+(v?' running':'')}
async function runSingle(){if(running)return;setRunning(true);const r=await fetch('/run/match',{method:'POST'});const d=await r.json();updateBoard(d.standings);updateReplay(d.hands);setRunning(false)}
async function runTournament(){if(running)return;setRunning(true);const r=await fetch('/run/tournament',{method:'POST'});const d=await r.json();updateBoard(d.standings);document.getElementById('rlabel').textContent='Tournament complete — top '+d.finalists+' finalists selected';setRunning(false)}
function updateBoard(standings){const b=document.getElementById('board');b.innerHTML='<div class="row hdr"><span>#</span><span>Bot</span><span>Chip delta</span><span>Matches</span></div>';const mx=Math.max(...standings.map(s=>Math.abs(s.cumulative_delta)),1);standings.forEach((s,i)=>{const d=s.cumulative_delta;const pct=Math.min(Math.abs(d)/mx*100,100);const sign=d>=0?'+':'';const dc=d>=0?'pos':'neg';b.innerHTML+=`<div class="row"><span style="color:${i<3?'#00ff41':'#3a6e3a'}">${i+1}</span><span>${s.bot_id}</span><span class="${dc}">${sign}${d.toLocaleString()}</span><span style="color:#3a6e3a">${s.matches_played}</span></div><div style="padding:0 0 4px 36px"><div class="bar-wrap"><div class="bar" style="width:${pct}%;${d<0?'background:#ff4444':''}"></div></div></div>`})}
function updateReplay(hands){if(!hands||!hands.length)return;const el=document.getElementById('replay');el.innerHTML='';document.getElementById('hcount').textContent='('+hands.length+' hands)';hands.slice(-20).reverse().forEach(h=>{const r=h;const winner=(r.winners||[]).map(w=>w.bot_id).join(', ')||'?';const comm=(r.community_cards||[]).join(' ')||'—';const acts=(r.action_log||[]).filter(a=>!['small_blind','big_blind'].includes(a.action)).slice(-6);let html=`<div class="hcard"><div class="hmeta">Hand #${(h.hand_num||0)+1} · ${r.street} · pot ${(r.pot||0).toLocaleString()} · winner: ${winner}</div>`;if(comm!=='—')html+=`<div class="community">${comm}</div>`;acts.forEach(a=>{const cls=a.action==='fold'?'fold':a.action==='raise'?'raise':'';const amt=a.amount?` ${a.amount.toLocaleString()}`:'';html+=`<div class="aline ${cls}">seat${a.seat} ${a.action}${amt}</div>`});html+='</div>';el.innerHTML+=html})}
</script></body></html>"""

@app.route("/")
def index(): return render_template_string(PAGE)

@app.route("/stream")
def stream():
    def generate():
        last = 0
        while True:
            with log_lock:
                new = state["log"][last:]; last = len(state["log"])
            for entry in new:
                yield f"data: {json.dumps(entry)}\n\n"
            time.sleep(0.2)
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.route("/run/match", methods=["POST"])
def run_single_match():
    emit("Starting 6-bot match...", "dim")
    t0 = time.time()
    result = run_match(f"demo_{uuid.uuid4().hex[:8]}", BOT_PATHS, n_hands=150)
    emit(f"Match complete in {time.time()-t0:.1f}s — {result['n_hands']} hands", "dim")
    all_results = []
    for bid, delta in result["chip_delta"].items():
        all_results.append({"bot_id": bid, "bot_path": BOT_PATHS.get(bid,""), "chip_delta": delta})
    for bid, delta in sorted(result["chip_delta"].items(), key=lambda x: -x[1]):
        sign = "+" if delta >= 0 else ""
        emit(f"  {bid:22s} {sign}{delta:,}", "win" if delta > 0 else "err" if delta < 0 else "dim")
    prev = [{"bot_id": s["bot_id"], "bot_path": s.get("bot_path",""), "chip_delta": s["cumulative_delta"]}
            for s in state["standings"]]
    state["standings"] = compute_standings(prev + all_results)
    state["hands"] = result.get("hands", [])
    hands_for_client = [{"hand_num": h["hand_num"], **{k: h[k] for k in
        ["type","street","pot","community_cards","winners","action_log","final_stacks","revealed_cards"]
        if k in h}} for h in state["hands"]]
    return jsonify({"standings": state["standings"], "hands": hands_for_client})

@app.route("/run/tournament", methods=["POST"])
def run_tournament():
    bot_list = [{"bot_id": bid, "bot_path": path, "cumulative_delta": 0, "matches_played": 0}
                for bid, path in BOT_PATHS.items()]
    state["standings"] = []; all_results = []
    for rnd in range(1, 4):
        emit(f"=== ROUND {rnd} ===", "bold")
        standings = compute_standings(all_results) if all_results else bot_list
        tables = swiss_pairing(standings, table_size=min(6, len(bot_list)))
        emit(f"  {len(tables)} table(s)", "dim")
        for t_idx, table in enumerate(tables):
            paths = {b["bot_id"]: b["bot_path"] for b in table}
            emit(f"  Table {t_idx+1}: {', '.join(paths)}", "dim")
            result = run_match(f"r{rnd}_t{t_idx}", paths, n_hands=150)
            for bid, delta in result["chip_delta"].items():
                all_results.append({"bot_id": bid, "bot_path": BOT_PATHS.get(bid,""), "chip_delta": delta})
                sign = "+" if delta >= 0 else ""
                emit(f"    {bid:22s} {sign}{delta:,}", "win" if delta > 0 else "err" if delta < 0 else "dim")
    state["standings"] = compute_standings(all_results)
    finalists = select_finalists(state["standings"], n=3)
    emit("=== FINALISTS ===", "bold")
    for i, f in enumerate(finalists):
        emit(f"  #{i+1} {f['bot_id']}  ({f['cumulative_delta']:+,})", "win")
    return jsonify({"standings": state["standings"], "round": 3, "finalists": len(finalists), "hands": []})

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  FULLHOUSE HACKATHON — LOCAL DEMO")
    print("="*50)
    print("  Open:  http://localhost:5000")
    print("="*50 + "\n")
    app.run(debug=False, threaded=True, port=5000)
'''

# ── __init__.py files ─────────────────────────────────────────────────────────
for path in ["engine/__init__.py", "sandbox/__init__.py", "matchqueue/__init__.py"]:
    files[path] = ""

# ── Write everything ──────────────────────────────────────────────────────────
print(f"\nCreating project at: {BASE}\n")
for rel_path, content in files.items():
    full_path = os.path.join(BASE, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as f:
        f.write(content)
    print(f"  wrote {rel_path}")

print(f"""
Done! Now run:

  cd ~/Desktop/fullhouse
  python3 demo.py

Then open http://localhost:5000 in your browser.
""")
