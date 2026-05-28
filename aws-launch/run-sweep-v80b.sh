#!/bin/bash
# Run V80b sweep (60 params, anchored to 7.13 defaults) on c7i.48xlarge.
# Wrap in tmux so the sweep survives SSH disconnects:
#   tmux new -s sweep
#   bash aws-launch/run-sweep-v80b.sh
#   (detach: Ctrl-b d ; reattach: tmux a -t sweep)
set -euo pipefail

cd ~/fullhouse-engine
source ~/.venv/bin/activate

# 192 vCPU on c7i.48xlarge — start at full whack (async harness handled
# 80 concurrent locally; user instruction: start high, drop if it fails).
#   n_jobs=12 parallel trials × workers=16 each = 192 concurrent matches
N_JOBS=${N_JOBS:-12}
N_WORKERS=${N_WORKERS:-16}
N_TRIALS=${N_TRIALS:-5000}
N_SEEDS=${N_SEEDS:-40}
N_HANDS=${N_HANDS:-200}
HU_SEEDS=${HU_SEEDS:-10}
N_TABLES=${N_TABLES:-15}
BATCH_SIZE=${BATCH_SIZE:-10}
# AUTO_TERMINATE=1 issues `sudo shutdown -h now` after sweep finishes.
# Combined with instance-initiated-shutdown-behavior=terminate, this kills
# the instance so we don't pay for idle hours overnight.
AUTO_TERMINATE=${AUTO_TERMINATE:-1}

DB_PATH=/home/ubuntu/fullhouse-engine/harness/results/skb80b.db
mkdir -p "$(dirname $DB_PATH)"
# WAL mode required for n_jobs>1 parallel writes without SQLite lock errors.
sqlite3 "$DB_PATH" "PRAGMA journal_mode=WAL; PRAGMA busy_timeout=30000;"
echo "DB journal mode: $(sqlite3 $DB_PATH 'PRAGMA journal_mode;')"
STORAGE_URL="sqlite:///${DB_PATH}"

echo "==== Sweep config ===="
echo "  trials:   $N_TRIALS"
echo "  seeds:    $N_SEEDS  (HU polish: $HU_SEEDS)"
echo "  hands:    $N_HANDS"
echo "  n_jobs:   $N_JOBS"
echo "  workers:  $N_WORKERS  (total concurrent: $((N_JOBS * N_WORKERS)))"
echo "  tables:   $N_TABLES"
echo "  auto-terminate: $AUTO_TERMINATE"
echo "======================"

python -m harness.sweep \
    --param-set v80 \
    --hu-seeds $HU_SEEDS \
    --trials $N_TRIALS \
    --seeds $N_SEEDS \
    --batch-size $BATCH_SIZE \
    --hands $N_HANDS \
    --workers $N_WORKERS \
    --n-jobs $N_JOBS \
    --mode 6max \
    --n-tables $N_TABLES \
    --study-name skb80b \
    --storage "$STORAGE_URL" \
    2>&1 | tee ~/sweep.log

echo "Sweep finished at $(date)" | tee -a ~/sweep.log
if [ "$AUTO_TERMINATE" = "1" ]; then
    echo "AUTO_TERMINATE=1 — shutting down in 60s. Cancel with: sudo shutdown -c" | tee -a ~/sweep.log
    sudo shutdown -h +1
fi
