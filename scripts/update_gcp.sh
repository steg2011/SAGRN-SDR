#!/bin/bash
#
# SAGRN SDR Monitor - Update Script
# Run this script to update to the latest version
#
# Usage: sudo ./update_gcp.sh
#

set -e

APP_DIR="/opt/sagrn-sdr"
APP_USER="sagrn"
BRANCH="main"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (use sudo)"
    exit 1
fi

log_info "Stopping SAGRN SDR service..."
systemctl stop sagrn-sdr

log_info "Pulling latest changes..."
cd "$APP_DIR"
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH"

log_info "Updating Python dependencies..."
cd "$APP_DIR/backend"
source venv/bin/activate
pip install -r requirements.txt
deactivate

log_info "Verifying frontend build..."
cd "$APP_DIR/frontend"

if [ ! -d "build" ] || [ ! -f "build/index.html" ]; then
    echo "Pre-built frontend missing after update!"
    echo "This may indicate an incomplete git pull."
    echo "Try: cd $APP_DIR && git pull origin main --force"
    exit 1
fi

log_info "✓ Frontend verified (pre-built)"

log_info "Setting permissions..."
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

log_info "Starting service..."
systemctl start sagrn-sdr

sleep 2

if systemctl is-active --quiet sagrn-sdr; then
    log_info "Update complete! Service is running."
    systemctl status sagrn-sdr --no-pager | head -5
else
    echo "Service failed to start. Check: journalctl -u sagrn-sdr -f"
    exit 1
fi
