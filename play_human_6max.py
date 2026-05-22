import sys
import os
import random
import argparse

os.environ["ACTION_TIMEOUT"] = "999999"
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from sandbox.match import run_match
from harness.opponents.registry import load_pool

parser = argparse.ArgumentParser(description="Play 6-max against skantbot + 4 random opponents")
parser.add_argument("--bot", default="skantbot7.7",
                    help="Skantbot version to include (default: skantbot7.7). Examples: skantbot7, skantbot7.3")
parser.add_argument("--hands", type=int, default=200, help="Hands per match (default: 200)")
parser.add_argument("--seed", type=int, default=None, help="Optional seed for reproducible deck + opponent draw")
args = parser.parse_args()

opp_path = f"bots/{args.bot}/bot.py"
if not os.path.isfile(opp_path):
    print(f"ERROR: bot file not found at {opp_path}")
    sys.exit(1)

if args.seed is not None:
    random.seed(args.seed)

pool = load_pool(include_heldout=True)
available_bots = list(pool.items())
selected_opponents = random.sample(available_bots, 4)

bots_list = [
    ("human", "bots/human_cli/bot.py"),
    (args.bot, opp_path)
] + selected_opponents
random.shuffle(bots_list)
bots = dict(bots_list)

print(f"Starting 6-max match with {args.bot} ({args.hands} hands)...")
print("\nYour Table Lineup:")
for i, (name, _) in enumerate(bots.items()):
    marker = " (You)" if name == "human" else ""
    print(f"  Seat {i}: {name}{marker}")

print("\nPress Ctrl+C to quit anytime.")

try:
    res = run_match(f"human_vs_{args.bot}_6max", bots, n_hands=args.hands, seed=args.seed)
    print("\nMatch finished successfully.")
    print("Chip deltas:", res.get("chip_delta", {}))
except KeyboardInterrupt:
    print("\nMatch aborted by user.")
except Exception as e:
    print(f"Error running match: {e}")
