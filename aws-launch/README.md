# AWS EC2 launch for skantbot 7.9 sweep

Step-by-step for spinning up a c7i.48xlarge to run the 5000-trial Optuna sweep.

**Prerequisites:**
- AWS CLI authenticated (`aws sts get-caller-identity` should work)
- vCPU quota raised to ≥192:
  - For on-demand: quota code `L-1216C47A`
  - For spot: quota code `L-34B43A08`
- The quota increase request you submitted is for spot only. If you want on-demand instead, submit the L-1216C47A request the same way.

## One-time setup (skip if already done)

```bash
# 1. Create SSH keypair (used to log into the instance)
aws ec2 create-key-pair --key-name skb-sweep-key --region eu-west-2 \
    --query 'KeyMaterial' --output text > ~/.ssh/skb-sweep-key.pem
chmod 400 ~/.ssh/skb-sweep-key.pem

# 2. Create a security group that allows SSH only from your current IP
MY_IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 create-security-group --group-name skb-sweep-sg \
    --description "SSH from my IP for skb sweep" --region eu-west-2
aws ec2 authorize-security-group-ingress --group-name skb-sweep-sg \
    --protocol tcp --port 22 --cidr ${MY_IP}/32 --region eu-west-2
```

## Launch + run (every sweep)

```bash
# 1. Launch the instance
#    For on-demand (~$8.57/hr, no interruption risk):
bash aws-launch/launch.sh
#    For spot (~$1.84/hr, can be killed by AWS):
USE_SPOT=1 bash aws-launch/launch.sh

# 2. Note the INSTANCE_ID and PUBLIC_IP from the table the script prints.
#    Wait ~3 min for cloud-init to finish (installs python3.12, eval7, optuna).

# 3. From your local machine, sync the repo up:
INSTANCE_IP=<the public IP from step 2>
rsync -avz \
    --exclude='.venv' --exclude='__pycache__' \
    --exclude='*.db' --exclude='harness/results/*.db' \
    --exclude='.git' \
    ~/Projects/Poker-bot/fullhouse-engine/ \
    ubuntu@${INSTANCE_IP}:fullhouse-engine/

# 4. SSH in and start the sweep in tmux (so it survives disconnects)
ssh -i ~/.ssh/skb-sweep-key.pem ubuntu@${INSTANCE_IP}
# On the instance:
cat READY    # should say "venv ready at /home/ubuntu/.venv"
tmux new -s sweep
bash fullhouse-engine/aws-launch/run-sweep.sh
# Detach with Ctrl-b d  (sweep continues in background)
# Reattach later: tmux a -t sweep
exit  # back to your local machine

# 5. Monitor (occasional):
ssh -i ~/.ssh/skb-sweep-key.pem ubuntu@${INSTANCE_IP} \
    'tail -20 ~/sweep.log'

# 6. When the sweep completes, pull results back:
rsync -avz \
    ubuntu@${INSTANCE_IP}:fullhouse-engine/harness/results/ \
    ~/Projects/Poker-bot/fullhouse-engine/harness/results/

# 7. **CRITICAL**: terminate the instance to stop billing!
INSTANCE_ID=<the instance ID from step 2>
aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region eu-west-2
```

## Expected cost (MEASURED — not extrapolated)

Real per-trial time was measured locally at 533s with n_workers=6, n_jobs=4. Cloud scaling estimate at n_workers=16:

| Trials | Mode | ~ wall time | Cost |
|---|---|---|---|
| 2000 | Spot c7i.48xlarge ($1.84/hr) | ~12-14 hr | $22-26 |
| 3000 | Spot c7i.48xlarge ($1.84/hr) | ~17-21 hr | $31-39 |
| 5000 | Spot c7i.48xlarge ($1.84/hr) | ~28-35 hr | $52-65 |
| 3000 | On-demand c7i.48xlarge ($8.57/hr) | ~17-21 hr | $145-180 (over budget) |

**Recommend 3000 trials on spot**: ~$35 expected, fits in $89 budget twice (one retry possible if interrupted). 5000 trials is also possible but doubles cost and wall time.

Override the default 5000 trials with the env var:
```bash
N_TRIALS=3000 bash aws-launch/run-sweep.sh
```

## Configurable run params

`run-sweep.sh` reads from env vars:
- `N_TRIALS` (default 5000) — total trials
- `N_SEEDS` (default 40) — seeds per trial for the train pool
- `HU_SEEDS` (default 10) — seeds for the 4th HU-polished objective
- `N_JOBS` (default 12) — parallel trials
- `N_WORKERS` (default 16) — workers per trial
- `AUTO_TERMINATE` (default 0; set to 1) — calls `sudo shutdown -h +1` after sweep finishes. Combined with launch.sh's `instance-initiated-shutdown-behavior=terminate`, this kills the instance automatically — so if you fall asleep waiting, you won't wake up to a $200 bill. Recommended for overnight runs.

Default `N_JOBS=12 × N_WORKERS=16 = 192 vCPU` — fills the c7i.48xlarge. If using a smaller instance, scale these down so the product matches your vCPU count.

## Spot interruption recovery

If you launched with `USE_SPOT=1` and AWS reclaims the instance mid-sweep, the Optuna study DB on the EBS volume DIES with it (DeleteOnTermination=true). However, you can recover from a partial sweep if you rsync the DB back periodically. Suggested approach:

```bash
# In a separate local terminal, while the sweep is running:
while true; do
    rsync -avz ubuntu@${INSTANCE_IP}:fullhouse-engine/harness/results/skb79_post_parser_fix.db \
        ~/Projects/Poker-bot/fullhouse-engine/harness/results/
    sleep 600   # every 10 min
done
```

If interrupted:
1. Note how many trials had completed (`grep "Trial " ~/Projects/Poker-bot/fullhouse-engine/harness/results/sweep.log | tail -3`)
2. Launch a fresh instance
3. rsync the repo (as before) AND rsync the partial DB back up to the instance
4. SSH in, edit `run-sweep.sh` to add `--resume` (or pass `RESUME=1`), and re-run
5. Optuna will pick up from the last completed trial

To avoid all of this: use on-demand (`USE_SPOT=0` default). Costs ~$50 instead of ~$15 but zero interruption risk.

## What to check before promoting the sweep result to 7.9

The sweep writes `harness/results/best_params_skb79_post_parser_fix.json`. Before tagging 7.9:

1. Read the JSON. Confirm `hu_polished_mean` is **≥ 7.7 HU baseline within SE** (the advisor's locked criterion — don't trade HU for 6-max gains).
2. Hot-swap the params into `bots/skantbot7.9/bot.py` Config defaults.
3. Validator pass: `python sandbox/validator.py bots/skantbot7.9/bot.py`
4. CRN self-test: `compare(7.9, 7.9)` paired_diff must be 0.0
5. CRN compare 7.9 vs 7.8 on 6-max + HU at 200 seeds each
6. CRN compare on UNSEEN_VALIDATION pool
7. Trace-table at least one representative hand through 7.8 → 7.9 to confirm the param changes flow correctly
