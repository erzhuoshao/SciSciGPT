#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run with sudo${NC}"
    echo "Usage: sudo bash $0"
    exit 1
fi

echo -e "${YELLOW}Stopping and disabling SciSciGPT services...${NC}"

systemctl stop sciscigpt-backend-restart.timer 2>/dev/null || true
systemctl stop sciscigpt-frontend-restart.timer 2>/dev/null || true
systemctl stop sciscigpt-ngrok.service 2>/dev/null || true
systemctl stop sciscigpt-frontend.service 2>/dev/null || true
systemctl stop sciscigpt-backend.service 2>/dev/null || true

systemctl disable sciscigpt-backend.service 2>/dev/null || true
systemctl disable sciscigpt-frontend.service 2>/dev/null || true
systemctl disable sciscigpt-backend-restart.timer 2>/dev/null || true
systemctl disable sciscigpt-ngrok.service 2>/dev/null || true
systemctl disable sciscigpt-frontend-restart.timer 2>/dev/null || true

echo -e "${YELLOW}Removing service files...${NC}"
rm -f /etc/systemd/system/sciscigpt-backend.service
rm -f /etc/systemd/system/sciscigpt-frontend.service
rm -f /etc/systemd/system/sciscigpt-backend-restart.service
rm -f /etc/systemd/system/sciscigpt-backend-restart.timer
rm -f /etc/systemd/system/sciscigpt-frontend-restart.service
rm -f /etc/systemd/system/sciscigpt-frontend-restart.timer
rm -f /etc/systemd/system/sciscigpt-ngrok.service

systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

echo -e "${GREEN}SciSciGPT services uninstalled.${NC}"
