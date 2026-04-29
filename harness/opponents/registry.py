"""
Bot pool registry.

    load_pool(include_heldout=False) -> {bot_id: absolute_bot_path}
    validate_pool(pool)              -> raises FileNotFoundError if any path missing

Training pool  (default): 4 reference bots + 1 archetype = 5 opponents
Full pool      (include_heldout=True): + 5 heldout = 10 opponents

SKANTBOT3_PATH: absolute path to bots/skantbot3/bot (1).py (space in name).
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
# Heldout bots — NEVER used in Optuna sweeps, only for final validation
# ---------------------------------------------------------------------------
# NOTE: The held-out set will be populated purely with 5 randomly chosen
# LLM-generated bots once they are created.
_HELDOUT = {}

# ---------------------------------------------------------------------------
# Convenience: absolute path to skantbot3 (filename has a space)
# ---------------------------------------------------------------------------
SKANTBOT3_PATH = str(_REPO_ROOT / "bots" / "skantbot3" / "bot (1).py")

# Path to the importlib shim (space-free wrapper around skantbot3)
SKANTBOT_TUNABLE_PATH = str(_REPO_ROOT / "harness" / "skantbot_tunable" / "bot.py")


def load_pool(include_heldout: bool = False) -> dict:
    """
    Return {bot_id: absolute_path} for the evaluation pool.

    Default (include_heldout=False): 4 reference + 1 archetype = 5 training opponents.
    With include_heldout=True:       + 5 heldout bots = 10 total.
    """
    pool = {}
    pool.update(_REFERENCE)
    pool.update(_ARCHETYPES_TRAIN)
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
