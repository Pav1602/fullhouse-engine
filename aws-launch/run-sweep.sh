#!/bin/bash
# Run on the EC2 instance, after rsync'ing the repo.
# Wrap in tmux so the sweep survives SSH disconnects:
#   tmux new -s sweep
#   bash aws-launch/run-sweep.sh
#   (detach with Ctrl-b d ; reattach with `tmux a -t sweep`)
set -euo pipefail

cd ~/fullhouse-engine
source ~/.venv/bin/activate

# 192 vCPU on c7i.48xlarge:
#   n_jobs=12 parallel trials × workers=16 each = 192
# Tune n_jobs vs workers if you change instance size.
N_JOBS=${N_JOBS:-12}
N_WORKERS=${N_WORKERS:-16}
N_TRIALS=${N_TRIALS:-3000}    # 5000 doubles wall time + cost; 3000 fits $89 budget with retry headroom
N_SEEDS=${N_SEEDS:-40}
HU_SEEDS=${HU_SEEDS:-10}
# AUTO_TERMINATE=1 issues `sudo shutdown -h now` after sweep finishes
# (combined with instance-initiated-shutdown-behavior=terminate, this kills
# the instance so you don't get billed for idle hours overnight).
AUTO_TERMINATE=${AUTO_TERMINATE:-0}

# WAL mode for SQLite — required for n_jobs>1 parallel writes without lock errors.
# SQLAlchemy URL params don't reliably activate WAL; set via PRAGMA on the
# file itself before Optuna opens it. WAL mode persists in the DB header.
DB_PATH=/home/ubuntu/fullhouse-engine/harness/results/skb79_post_parser_fix.db
mkdir -p "$(dirname $DB_PATH)"
sqlite3 "$DB_PATH" "PRAGMA journal_mode=WAL; PRAGMA busy_timeout=30000;"
echo "DB journal mode: $(sqlite3 $DB_PATH 'PRAGMA journal_mode;')"
STORAGE_URL="sqlite:///${DB_PATH}"

python -m harness.sweep \
    --param-set v79 \
    --hu-seeds $HU_SEEDS \
    --trials $N_TRIALS \
    --seeds $N_SEEDS \
    --batch-size 10 \
    --hands 200 \
    --workers $N_WORKERS \
    --n-jobs $N_JOBS \
    --mode 6max \
    --n-tables 15 \
    --study-name skb79_post_parser_fix \
    --storage "$STORAGE_URL" \
    2>&1 | tee ~/sweep.log

echo "Sweep finished at $(date)" | tee -a ~/sweep.log
if [ "$AUTO_TERMINATE" = "1" ]; then
    echo "AUTO_TERMINATE=1 — shutting down in 60s. Cancel with: sudo shutdown -c" | tee -a ~/sweep.log
    sudo shutdown -h +1
fi
