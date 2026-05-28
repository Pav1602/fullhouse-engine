# V80b Sweep — Tomorrow Morning Checklist

## State at session end (Thu 23:00 UTC ≈ Fri 00:00 BST)
- Instance: `i-032a8a76cb95f04e2` (spot c7i.48xlarge, eu-west-2, IP 3.10.234.192)
- Sweep: `skb80b`, V80b param space (60 params), 5000 trials target
- Anchor: 7.13 defaults enqueued as trial 0
- Steady state: **~33s/trial @ 91% CPU during match work**
- Bot: skantbot7.13 dev (in-process via the ProcessPool harness)
- DB snapshot: `harness/results/sweep_db_snapshots/skb80b_0000.db`
- AUTO_TERMINATE=1: instance will self-kill ~60s after sweep completes (or fails)

## Step 1 — Pull latest DB (one-liner)
```bash
INSTANCE_IP=3.10.234.192
rsync -avz -e "ssh -i ~/.ssh/skb-sweep-key.pem -o StrictHostKeyChecking=no" \
  ubuntu@$INSTANCE_IP:fullhouse-engine/harness/results/skb80b.db \
  harness/results/sweep_db_snapshots/skb80b_$(date +%H%M).db
```

## Step 2 — Check progress
```bash
ssh -i ~/.ssh/skb-sweep-key.pem ubuntu@$INSTANCE_IP \
  "grep -c 'Trial.*finished' ~/sweep.log; grep 'Trial.*finished' ~/sweep.log | tail -3"
```

## Step 3 — Quick analysis (DOES THE SWEEP LOOK USEFUL?)

```bash
.venv/bin/python -c "
import optuna
study = optuna.load_study(
    study_name='skb80b',
    storage='sqlite:///harness/results/sweep_db_snapshots/skb80b_<HHMM>.db')
trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
print(f'{len(trials)} complete trials')

# Best by train_mean (objective 0)
top = sorted(trials, key=lambda t: -t.values[0])[:10]
print('\nTop 10 by train_mean:')
for t in top:
    print(f'  #{t.number}: train={t.values[0]:.0f}  worst={t.values[1]:.0f}  unseen={t.values[2]:.0f}')

# Direction check: did key params move?
anchor = next(t for t in trials if t.number == 0)
best = top[0]
print(f'\nKey params: anchor (7.13) vs best trial')
for k in ['equity_call_threshold','pot_odds_buffer_normal','cbet_freq_base',
         'bluff_freq_ip','threebet_call_threshold_pct','fourbet_call_threshold_pct',
         'k_commit','spr_commit_threshold']:
    a = anchor.params.get(k)
    b = best.params.get(k)
    direction = '↑' if b > a else '↓' if b < a else '='
    print(f'  {k:35} 7.13={a:.4f}  best={b:.4f}  {direction}')
"
```

**Direction expectations from V80b priors:**
- `equity_call_threshold` ↑ (tighter postflop calling, closes hero-call)
- `pot_odds_buffer_normal` ↑ (more eq required vs pot odds)
- `cbet_freq_base` ↓ (Mode A reduction)
- `bluff_freq_ip` ↓ (Mode A reduction)
- `bluff_freq_oop` ↓ (Mode A reduction)
- `threebet_call_threshold_pct` ↓ (tighter preflop defense)
- `fourbet_call_threshold_pct` ↓ (tighter preflop defense)
- `k_commit` ↓ (less aggressive commitment regime)

If most directions match priors → sweep is working as expected → consider promoting best trial to 7.14.
If they're random → priors may be wrong OR convergence not yet → keep running.

## Step 4 — Decide

### (a) Sweep is converging well → STOP + verify best trial
```bash
# Kill sweep cleanly (so instance doesn't auto-terminate before we analyze)
ssh -i ~/.ssh/skb-sweep-key.pem ubuntu@$INSTANCE_IP \
  "tmux send-keys -t sweep C-c; sleep 5; tmux kill-server"

# Pull final DB
rsync -avz -e "ssh -i ~/.ssh/skb-sweep-key.pem" \
  ubuntu@$INSTANCE_IP:fullhouse-engine/harness/results/skb80b.db \
  harness/results/

# Terminate instance
aws ec2 terminate-instances --instance-ids i-032a8a76cb95f04e2 --region eu-west-2

# Then in conversation: ask Claude to build 7.14 from the best trial params,
# verify CRN, paired-diff vs 7.13, paper hands, bust survey
```

### (b) Need more trials → KEEP RUNNING
Just leave it. Check again in a few hours. The sweep will hit 5000 trials and the instance will auto-terminate.

### (c) Sweep looks like it's wandering → resume with different sampler / smaller param space
Stop, analyze why TPE isn't converging (too many params, params not actually loadbearing, etc.). Restart with a more focused V80c.

## Files to read
- `REMEDIATION_7.12_3bettor_path.md` — 7.12 reasoning
- Git log: `260d1c8` (7.12), `aad7256` (7.13), `dce61ee` (V80 + anchor), `03caab1` (V80b)
- `harness/sweep.py` lines 145–230 — V80b PARAM_SPACE_V80 definition

## If something is wrong
- Instance unreachable: `aws ec2 describe-instance-status --instance-ids i-032a8a76cb95f04e2 --region eu-west-2`
- Spot interrupted: snapshot has data through 23:58 UTC; can resume with `--resume` flag if instance comes back

## Cost so far
- Instance launched: ~22:14 UTC Thu
- Spot rate: ~$1.84/hr
- Through 9am Fri BST = ~11hr × $1.84 = ~$20
- Plus instance overhead: ~$2-3
- Total estimated cost at morning checkpoint: ~$22-25
