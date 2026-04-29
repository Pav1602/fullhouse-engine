"""
Thin importlib shim for bots/skantbot4/bot.py

This file exists to give skantbot4 a path without spaces, making it safe to
pass to sandbox/match.py and reference from CLI commands without shell quoting.

For Optuna sweeps the sweep worker sets SKANT_* environment variables BEFORE
calling run_match(). Those vars are inherited by the BotProcess subprocess via
env={**os.environ, ...} in BotProcess._start(). The subprocess runs runner.py
which calls load_bot(BOT_PATH) → imports this shim → exec_module() runs
skantbot4 top-level code → CONFIG = load_config_from_env() reads the overrides.

DO NOT set SKANT_* vars inside this file. The sweep worker is responsible for
setting them in the environment before spawning match workers.
"""

import importlib.util
import sys
from pathlib import Path

_SKANTBOT4_PATH = str(
    Path(__file__).parent.parent.parent / "bots" / "skantbot4" / "bot.py"
)

_spec = importlib.util.spec_from_file_location("skantbot4_module", _SKANTBOT4_PATH)
_mod  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

BOT_NAME   = getattr(_mod, "BOT_NAME",   "SkantBot4_Tunable")
BOT_AVATAR = getattr(_mod, "BOT_AVATAR", "robot_1")


def decide(game_state: dict) -> dict:
    return _mod.decide(game_state)
