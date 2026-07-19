#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$DEPLOY_DIR")"

echo -e "${GREEN}=== SciSciGPT Systemd Deployment ===${NC}"
echo "Deploy dir: $DEPLOY_DIR"
echo "Project dir: $PROJECT_DIR"

# Check we're running with sudo/root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run with sudo${NC}"
    echo "Usage: sudo bash $0"
    exit 1
fi

# Verify required paths exist
echo -e "${YELLOW}Checking prerequisites...${NC}"
REQUIRED_PATHS=(
    "/home/shaoerzhuo/anaconda3/envs/sciscigpt/bin/uvicorn"
    "/home/shaoerzhuo/anaconda3/envs/sciscigpt/bin/python"
    "/home/shaoerzhuo/anaconda3/envs/sciscigpt/bin/node"
    "/home/shaoerzhuo/anaconda3/envs/sciscigpt/bin/pnpm"
    "$PROJECT_DIR/backend/app.py"
    "$PROJECT_DIR/backend/.env"
    "$PROJECT_DIR/frontend/package.json"
)

for path in "${REQUIRED_PATHS[@]}"; do
    if [ ! -e "$path" ]; then
        echo -e "${RED}Error: Required path not found: $path${NC}"
        exit 1
    fi
    echo "  OK: $path"
done

# Reset failed state (needed if a service hit StartLimitBurst)
echo -e "${YELLOW}Resetting failed services (if any)...${NC}"
systemctl reset-failed sciscigpt-backend.service 2>/dev/null || true
systemctl reset-failed sciscigpt-frontend.service 2>/dev/null || true
systemctl reset-failed sciscigpt-ngrok.service 2>/dev/null || true

# Stop existing services if running
echo -e "${YELLOW}Stopping existing services (if any)...${NC}"
systemctl stop sciscigpt-backend-restart.timer 2>/dev/null || true
systemctl stop sciscigpt-frontend-restart.timer 2>/dev/null || true
systemctl stop sciscigpt-ngrok.service 2>/dev/null || true
systemctl stop sciscigpt-frontend.service 2>/dev/null || true
systemctl stop sciscigpt-backend.service 2>/dev/null || true

# Copy service and timer files
echo -e "${YELLOW}Installing service files...${NC}"
cp "$DEPLOY_DIR/sciscigpt-backend.service" /etc/systemd/system/
cp "$DEPLOY_DIR/sciscigpt-frontend.service" /etc/systemd/system/
cp "$DEPLOY_DIR/sciscigpt-backend-restart.service" /etc/systemd/system/
cp "$DEPLOY_DIR/sciscigpt-backend-restart.timer" /etc/systemd/system/
cp "$DEPLOY_DIR/sciscigpt-frontend-restart.service" /etc/systemd/system/
cp "$DEPLOY_DIR/sciscigpt-frontend-restart.timer" /etc/systemd/system/
cp "$DEPLOY_DIR/sciscigpt-ngrok.service" /etc/systemd/system/

# Set correct permissions
chmod 644 /etc/systemd/system/sciscigpt-*.service
chmod 644 /etc/systemd/system/sciscigpt-*.timer

# Reload systemd daemon
echo -e "${YELLOW}Reloading systemd daemon...${NC}"
systemctl daemon-reload

# Enable services (auto-start on boot)
echo -e "${YELLOW}Enabling services...${NC}"
systemctl enable sciscigpt-backend.service
systemctl enable sciscigpt-frontend.service
systemctl enable sciscigpt-ngrok.service
systemctl enable sciscigpt-backend-restart.timer
systemctl enable sciscigpt-frontend-restart.timer

# Start services (--no-block so the script returns immediately)
echo -e "${YELLOW}Starting services...${NC}"
systemctl start --no-block sciscigpt-backend.service
echo "  Backend starting..."

systemctl start --no-block sciscigpt-frontend.service
echo "  Frontend starting (will build first, may take a few minutes)..."

systemctl start --no-block sciscigpt-ngrok.service
echo "  ngrok tunnel starting..."

# Start timers
systemctl start sciscigpt-backend-restart.timer
systemctl start sciscigpt-frontend-restart.timer
echo "  Daily restart timers started."

# Print status
echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "Service status:"
systemctl status sciscigpt-backend.service --no-pager -l || true
echo ""
systemctl status sciscigpt-frontend.service --no-pager -l || true
echo ""
systemctl status sciscigpt-ngrok.service --no-pager -l || true
echo ""
echo "Timer status:"
systemctl list-timers sciscigpt-* --no-pager || true
echo ""
echo -e "${GREEN}=== Useful Commands ===${NC}"
echo "  sudo systemctl status sciscigpt-backend"
echo "  sudo systemctl status sciscigpt-frontend"
echo "  sudo systemctl restart sciscigpt-backend"
echo "  sudo systemctl restart sciscigpt-frontend"
echo "  sudo systemctl status sciscigpt-ngrok"
echo "  sudo journalctl -u sciscigpt-backend -f"
echo "  sudo journalctl -u sciscigpt-frontend -f"
echo "  sudo journalctl -u sciscigpt-ngrok -f"
echo "  sudo systemctl list-timers sciscigpt-*"
