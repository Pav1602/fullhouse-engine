#!/bin/bash
# EC2 user-data — runs once at first boot as root.
# Installs Python 3.12, build tools, and prereqs for eval7 / optuna.
# Does NOT start the sweep; user uploads repo + runs manually.
set -euxo pipefail

# Log everything to /var/log/user-data.log
exec > >(tee -a /var/log/user-data.log) 2>&1

apt-get update
apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pip \
    build-essential \
    git \
    sqlite3 \
    tmux \
    rsync \
    htop

# Give 'ubuntu' user a working venv ready to go
sudo -u ubuntu bash <<'EOF'
cd /home/ubuntu
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install eval7 optuna numpy tqdm
echo "venv ready at /home/ubuntu/.venv" > /home/ubuntu/READY
EOF

# Mark cloud-init complete
touch /var/lib/cloud/instance/boot-finished
echo "user-data: COMPLETE at $(date)" >> /var/log/user-data.log
