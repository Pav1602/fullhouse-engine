# Skantbot 7.11 Logging Implementation

Opt-in structured JSON-lines logging has been successfully integrated into both the submission and dev versions of `skantbot7.11`. This captures detailed internal state values (`eq`, `v_range`, `pot_odds`, etc.) for every single decision, vastly accelerating future bust diagnostics.

## 1. How to Enable Logging
The submission bot ships with logging **OFF** by default (yielding zero file IO or performance overhead). To safely activate logging without breaking the validator constraints, use the **dev bot** and provide a file path via the `SKANT_LOG_PATH` environment variable:

```bash
SKANT_LOG_PATH=/tmp/skant_test.jsonl .venv/bin/python sandbox/match.py harness/skantbot7_11_dev/bot.py bots/skantbot7.9/bot.py --hands 10
```

## 2. Example Log Line
The output is written as JSONL (one JSON object per line). Below is a pretty-printed example of a log entry captured at the decision point:

```json
{
  "ts": 1779730338.1391823,
  "hand_id": "local_2d7c85cf_h0004",
  "street": "preflop",
  "seat": 0,
  "hole": ["5c", "Ac"],
  "board": [],
  "pot": 150,
  "owed": 50,
  "stack": 9950,
  "eq": null,
  "v_range_size": 0,
  "v_range_sample": [],
  "pot_odds": 0.25,
  "required_eq": null,
  "branch": "decide_preflop_hu_1654",
  "action": {"action": "raise", "amount": 201},
  "match_delta": 0,
  "opp_id": null,
  "opp_n_hands": null,
  "opp_rwf": null
}
```

## 3. Submission Safety Confirmed
- Running the `bots/skantbot7.11/bot.py` generates absolutely **no** log files (`ls -l *log* decision_log* skant_log*` confirms silent operation).
- The submission bot preserves CRN (Common Random Numbers), meaning no unseeded randomness disrupts sweeping tasks.
- Static AST limits are unbreached (the `import os` statement is strictly averted in the submission bot), resulting in `sandbox/validator.py` passing perfectly.
