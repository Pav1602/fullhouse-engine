"""
Bot pool registry.

    load_pool(include_heldout=False) -> {bot_id: absolute_bot_path}
    validate_pool(pool)              -> raises FileNotFoundError if any path missing

Training pool  (default): 4 reference bots + 6 archetypes + 7 LLM bots = 17 opponents
Full pool      (include_heldout=True): + 5 heldout LLM bots = 22 opponents
"""

from pathlib import Path

_HERE      = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent

# ---------------------------------------------------------------------------
# Reference bots (symlinks under harness/opponents/reference/)
# ---------------------------------------------------------------------------
_REFERENCE = {
    "aggressor":    str(_HERE / "reference" / "aggressor"    / "bot.py"),
    "mathematician": str(_HERE / "reference" / "mathematician" / "bot.py"),
    "ref_bot_2":    str(_HERE / "reference" / "ref_bot_2"    / "bot.py"),
    "shark":        str(_HERE / "reference" / "shark"         / "bot.py"),
}

# ---------------------------------------------------------------------------
# Archetype bots kept in the TRAINING pool
# ---------------------------------------------------------------------------
_ARCHETYPES_TRAIN = {
    "all_in_monkey":   str(_HERE / "archetypes" / "all_in_monkey" / "bot.py"),
    "calling_station": str(_HERE / "archetypes" / "calling_station" / "bot.py"),
    "limp_machine":    str(_HERE / "archetypes" / "limp_machine" / "bot.py"),
    "min_raiser":      str(_HERE / "archetypes" / "min_raiser" / "bot.py"),
    "super_nit":       str(_HERE / "archetypes" / "super_nit" / "bot.py"),
    "uniform_random":  str(_HERE / "archetypes" / "uniform_random" / "bot.py"),
}

# ---------------------------------------------------------------------------
# LLM-generated bots kept in the TRAINING pool
# ---------------------------------------------------------------------------
_LLM_GENERATED_TRAIN = {
    "chatgpt-2": str(_HERE / "llm_generated" / "chatgpt-2" / "bot.py"),
    "chatgpt-7": str(_HERE / "llm_generated" / "chatgpt-7" / "bot.py"),
    "claude-4":  str(_HERE / "llm_generated" / "claude-4" / "bot.py"),
    "deepseek-5": str(_HERE / "llm_generated" / "deepseek-5" / "bot.py"),
    "gemini-1":  str(_HERE / "llm_generated" / "gemini-1" / "bot.py"),
    "gemini-6":  str(_HERE / "llm_generated" / "gemini-6" / "bot.py"),
    "grok-3":    str(_HERE / "llm_generated" / "grok-3" / "bot.py"),
}

# ---------------------------------------------------------------------------
# Heldout bots — NEVER used in Optuna sweeps, only for final validation
# ---------------------------------------------------------------------------
_HELDOUT = {
    "chatgpt-12": str(_HERE / "llm_generated" / "chatgpt-12" / "bot.py"),
    "claude-9":   str(_HERE / "llm_generated" / "claude-9" / "bot.py"),
    "deepseek-10": str(_HERE / "llm_generated" / "deepseek-10" / "bot.py"),
    "gemini-11":  str(_HERE / "llm_generated" / "gemini-11" / "bot.py"),
    "grok-8":     str(_HERE / "llm_generated" / "grok-8" / "bot.py"),
}

# ---------------------------------------------------------------------------
# Convenience: absolute path to skantbot4 (latest bot)
# ---------------------------------------------------------------------------
SKANTBOT4_PATH = str(_REPO_ROOT / "bots" / "skantbot4" / "bot.py")

# Path to the dev bot for sweeps (with env loading)
SKANTBOT_TUNABLE_PATH = str(_REPO_ROOT / "harness" / "skantbot_dev" / "bot.py")


def load_pool(include_heldout: bool = False) -> dict:
    """
    Return {bot_id: absolute_path} for the evaluation pool.
    """
    pool = {}
    pool.update(_REFERENCE)
    pool.update(_ARCHETYPES_TRAIN)
    pool.update(_LLM_GENERATED_TRAIN)
    if include_heldout:
        pool.update(_HELDOUT)
    return pool


def validate_pool(pool: dict) -> None:
    """Raise FileNotFoundError if any bot path in the pool does not exist."""
    missing = [bot_id for bot_id, path in pool.items()
               if not Path(path).exists()]
    if missing:
        raise FileNotFoundError(
            f"Bot files not found for: {missing}\n"
            "Check that symlinks under harness/opponents/reference/ are intact."
        )