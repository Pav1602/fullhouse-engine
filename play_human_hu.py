import sys
import os

# OVERRIDE the engine's 2-second timeout so a human has time to think!
os.environ["ACTION_TIMEOUT"] = "999999"

# Add root to sys.path so we can import sandbox
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from sandbox.match import run_match

bots = {
    "human": "bots/human_cli/bot.py",
    "skantbot7": "bots/skantbot7/bot.py"
}

print("Starting Heads-Up match against Skantbot7...")
print("You are 'human'.")
print("Press Ctrl+C to quit anytime.")

try:
    res = run_match("human_vs_skantbot7_hu", bots, n_hands=200, seed=None)
    print("\nMatch finished successfully.")
    print("Chip deltas:", res.get("chip_delta", {}))
except KeyboardInterrupt:
    print("\nMatch aborted by user.")
except Exception as e:
    print(f"Error running match: {e}")
