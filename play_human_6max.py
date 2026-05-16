import sys
import os
import random

# OVERRIDE the engine's 2-second timeout so a human has time to think!
os.environ["ACTION_TIMEOUT"] = "999999"

# Add root to sys.path so we can import sandbox and harness
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from sandbox.match import run_match
from harness.opponents.registry import load_pool

# Load all bots from the expanded training and unseen pools
pool = load_pool(include_heldout=True)
available_bots = list(pool.items())

# Pick 4 random opponents
selected_opponents = random.sample(available_bots, 4)

# Create the final lineup including the human and skantbot7
bots_list = [
    ("human", "bots/human_cli/bot.py"),
    ("skantbot7", "bots/skantbot7/bot.py")
] + selected_opponents

# Shuffle the list so the human and skantbot aren't always in seats 0 and 1
random.shuffle(bots_list)
bots = dict(bots_list)

print("Starting 6-max match...")
print("\nYour Table Lineup:")
for i, (name, _) in enumerate(bots.items()):
    marker = " (You)" if name == "human" else ""
    print(f"  Seat {i}: {name}{marker}")

print("\nPress Ctrl+C to quit anytime.")

try:
    res = run_match("human_vs_skantbot7_6max", bots, n_hands=200, seed=None)
    print("\nMatch finished successfully.")
    print("Chip deltas:", res.get("chip_delta", {}))
except KeyboardInterrupt:
    print("\nMatch aborted by user.")
except Exception as e:
    print(f"Error running match: {e}")
