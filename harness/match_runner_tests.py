import sys
import unittest
from pathlib import Path
import os
import shutil

_REPO_ROOT = str(Path(__file__).parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from harness.match_runner import compare, aggregate_by_opponent

class TestMatchRunner(unittest.TestCase):
    def setUp(self):
        # We use purely deterministic bots for determinism checks so we test harness determinism
        self.bot_det = "bots/ref_bot_2/bot.py"
        self.bot_skant = "bots/skantbot7/bot.py"
        # Deterministic pool to isolate harness testing from bot-internal unseeded RNG (like aggressor's random.random())
        self.pool = {
            f"opp{i}": "bots/ref_bot_2/bot.py" for i in range(1, 7)
        }
        self.mixed_pool = {
            "opp1": "bots/shark/bot.py",
            "opp2": "bots/mathematician/bot.py",
            "opp3": "bots/ref_bot_2/bot.py",
            "opp4": "bots/aggressor/bot.py",
            "opp5": "bots/aggressor/bot.py",
            "opp6": "bots/shark/bot.py"
        }

    def test_hu_fallback_identity(self):
        res = compare(self.bot_det, self.bot_det, self.pool, n_seeds=5, n_hands=10, mode="hu")
        for opp, stats in res.items():
            self.assertEqual(stats["paired_diff_mean"], 0.0)
            
    def test_6max_self_comparison(self):
        res = compare(self.bot_det, self.bot_det, self.pool, n_seeds=5, n_hands=10, mode="6max", n_tables=3)
        for tid, stats in res.items():
            self.assertEqual(stats["paired_diff_mean"], 0.0)

    def test_6max_determinism(self):
        res1 = compare(self.bot_det, self.bot_det, self.pool, n_seeds=5, n_hands=10, mode="6max", n_tables=3, seed_offset=42)
        res2 = compare(self.bot_det, self.bot_det, self.pool, n_seeds=5, n_hands=10, mode="6max", n_tables=3, seed_offset=42)
        for tid in res1:
            self.assertEqual(res1[tid]["a_mean"], res2[tid]["a_mean"])
            
    def test_crn_sanity(self):
        os.makedirs("bots/tmp_test", exist_ok=True)
        shutil.copy("bots/skantbot7/bot.py", "bots/tmp_test/bot.py")
        res = compare("bots/skantbot7/bot.py", "bots/tmp_test/bot.py", self.pool, n_seeds=5, n_hands=10, mode="6max", n_tables=3)
        for tid, stats in res.items():
            # For skantbot7, variance is non-zero but small
            self.assertLess(abs(stats["paired_diff_stderr"]), 2500.0)
            
    def test_opponent_decomposition_consistency(self):
        res = compare(self.bot_det, self.bot_det, self.pool, n_seeds=5, n_hands=10, mode="6max", n_tables=3)
        agg = aggregate_by_opponent(res)
        for opp in self.pool:
            if opp in agg:
                self.assertTrue("a_mean" in agg[opp])

if __name__ == "__main__":
    unittest.main()
