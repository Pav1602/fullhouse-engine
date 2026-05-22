import sys
import os
import argparse

os.environ["ACTION_TIMEOUT"] = "999999"
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from sandbox.match import run_match

parser = argparse.ArgumentParser(description="Play heads-up against a skantbot")
parser.add_argument("--bot", default="skantbot7.6",
                    help="Bot to play against (default: skantbot7.6). Examples: skantbot7, skantbot7.3, skantbot4")
parser.add_argument("--hands", type=int, default=200, help="Hands per match (default: 200)")
parser.add_argument("--seed", type=int, default=None, help="Optional seed for reproducible deck")
args = parser.parse_args()

opp_path = f"bots/{args.bot}/bot.py"
if not os.path.isfile(opp_path):
    print(f"ERROR: bot file not found at {opp_path}")
    sys.exit(1)

bots = {"human": "bots/human_cli/bot.py", args.bot: opp_path}

print(f"Starting Heads-Up match against {args.bot} ({args.hands} hands)...")
print("You are 'human'.")
print("Press Ctrl+C to quit anytime.")

try:
    res = run_match(f"human_vs_{args.bot}_hu", bots, n_hands=args.hands, seed=args.seed)
    print("\nMatch finished successfully.")
    print("Chip deltas:", res.get("chip_delta", {}))
except KeyboardInterrupt:
    print("\nMatch aborted by user.")
except Exception as e:
    print(f"Error running match: {e}")
