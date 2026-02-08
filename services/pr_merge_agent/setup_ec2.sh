#!/bin/bash
set -e

# Configuration
APP_DIR=$(pwd)
VENV_DIR="$APP_DIR/.venv"
USER_NAME=$(whoami)
SERVICE_API="pr-merge-api"
SERVICE_WORKER="pr-merge-worker"

echo "=== pr_merge_agent EC2 Setup ==="
echo "App Directory: $APP_DIR"
echo "User: $USER_NAME"

# 1. Install System Dependencies (Amazon Linux 2023 / RHEL / CentOS)
if command -v dnf &> /dev/null; then
    echo "Detected dnf (Amazon Linux 2023 / Fedora)..."
    sudo dnf install -y python3 python3-pip git
elif command -v apt-get &> /dev/null; then
    echo "Detected apt-get (Ubuntu / Debian)..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-venv git
else
    echo "Unsupported package manager. Please ensure Python 3 and Git are installed."
fi

# 2. Setup Python Virtual Environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt

# 3. Create Systemd Service for API
echo "Creating systemd service: $SERVICE_API..."
cat <<EOF | sudo tee /etc/systemd/system/$SERVICE_API.service
[Unit]
Description=PR Merge Agent API
After=network.target

[Service]
User=$USER_NAME
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/uvicorn pr_merge_agent.app:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 4. Create Systemd Service for Worker
echo "Creating systemd service: $SERVICE_WORKER..."
cat <<EOF | sudo tee /etc/systemd/system/$SERVICE_WORKER.service
[Unit]
Description=PR Merge Agent Worker
After=network.target

[Service]
User=$USER_NAME
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/python -m pr_merge_agent.runner
Restart=always
# Restart slowly to avoid spamming if configuration is wrong
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 5. Enable and Start Services
echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "Enabling and starting $SERVICE_API..."
sudo systemctl enable $SERVICE_API
sudo systemctl restart $SERVICE_API

echo "Enabling and starting $SERVICE_WORKER..."
sudo systemctl enable $SERVICE_WORKER
sudo systemctl restart $SERVICE_WORKER

echo "=== Setup Complete ==="
echo "Check status directly:"
echo "  sudo systemctl status $SERVICE_API"
echo "  sudo systemctl status $SERVICE_WORKER"
echo "View logs:"
echo "  journalctl -u $SERVICE_API -f"
echo "  journalctl -u $SERVICE_WORKER -f"
