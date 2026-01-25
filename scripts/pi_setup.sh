#!/bin/bash
# SAGRN SDR Raspberry Pi Collector Setup Script
# Run this script on the Raspberry Pi to set up the pager collector

set -e

# Get current user (don't use $USER as it might be root when running with sudo)
CURRENT_USER=$(logname 2>/dev/null || whoami)
USER_HOME=$(eval echo ~$CURRENT_USER)

echo "==================================="
echo "SAGRN SDR Collector Setup"
echo "==================================="
echo "Installing for user: $CURRENT_USER"
echo "Home directory: $USER_HOME"
echo "==================================="

# Update system
echo "[1/6] Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install dependencies
echo "[2/6] Installing dependencies..."
sudo apt-get install -y \
    rtl-sdr \
    multimon-ng \
    python3 \
    python3-pip \
    python3-venv \
    git

# Create collector directory
echo "[3/6] Creating collector directory..."
mkdir -p ~/sagrn-collector
cd ~/sagrn-collector

# Create Python virtual environment
echo "[4/6] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install requests

# Copy collector script
echo "[5/6] Installing collector script..."
cat > collector.py << 'COLLECTOR_EOF'
#!/usr/bin/env python3
"""
SAGRN SDR Pager Collector
Reads from multimon-ng output and sends to the central server
"""

import subprocess
import requests
import sys
import time
import os
from datetime import datetime

# Configuration
SERVER_URL = os.environ.get('SAGRN_SERVER_URL', 'http://192.168.1.100:8000')
COLLECTOR_ID = os.environ.get('COLLECTOR_ID', 'pager1')
FREQUENCY = os.environ.get('PAGER_FREQUENCY', '148.1375M')  # SAGRN pager frequency
SAMPLE_RATE = '22050'

def send_message(message: str) -> bool:
    """Send a message to the central server"""
    try:
        response = requests.post(
            f'{SERVER_URL}/api/collector/message',
            json={
                'message': message,
                'collector_id': COLLECTOR_ID,
                'timestamp': datetime.utcnow().isoformat()
            },
            timeout=5
        )
        return response.status_code == 200
    except requests.RequestException as e:
        print(f"[ERROR] Failed to send message: {e}", file=sys.stderr)
        return False

def run_collector():
    """Run the SDR collector pipeline"""
    print(f"[INFO] Starting SAGRN collector '{COLLECTOR_ID}'")
    print(f"[INFO] Server: {SERVER_URL}")
    print(f"[INFO] Frequency: {FREQUENCY}")

    # RTL-SDR -> multimon-ng pipeline
    rtl_cmd = [
        'rtl_fm',
        '-f', FREQUENCY,
        '-s', SAMPLE_RATE,
        '-g', '40',
        '-p', '0',
        '-'
    ]

    multimon_cmd = [
        'multimon-ng',
        '-t', 'raw',
        '-a', 'FLEX',
        '-f', 'alpha',
        '-'
    ]

    print(f"[INFO] Starting RTL-SDR...")
    rtl_process = subprocess.Popen(
        rtl_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    print(f"[INFO] Starting multimon-ng...")
    multimon_process = subprocess.Popen(
        multimon_cmd,
        stdin=rtl_process.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Check if rtl_fm started successfully
    time.sleep(1)
    if rtl_process.poll() is not None:
        stderr = rtl_process.stderr.read().decode() if rtl_process.stderr else ''
        print(f"[ERROR] rtl_fm failed to start: {stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Collector running. Listening for pager messages...")

    message_count = 0
    try:
        for line in multimon_process.stdout:
            line = line.strip()
            if not line:
                continue

            # Skip non-message lines
            if line.startswith('multimon-ng') or line.startswith('Available') or line.startswith('Enabled'):
                continue

            message_count += 1
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Log locally
            print(f"[{timestamp}] {line}")

            # Send to server
            if send_message(line):
                print(f"[OK] Message {message_count} sent")
            else:
                print(f"[WARN] Message {message_count} failed to send")

    except KeyboardInterrupt:
        print("\n[INFO] Stopping collector...")
    finally:
        multimon_process.terminate()
        rtl_process.terminate()
        print(f"[INFO] Collector stopped. Total messages: {message_count}")

if __name__ == '__main__':
    run_collector()
COLLECTOR_EOF

chmod +x collector.py

# Create systemd service
echo "[6/6] Creating systemd service..."
sudo tee /etc/systemd/system/sagrn-collector.service > /dev/null << SERVICE_EOF
[Unit]
Description=SAGRN SDR Pager Collector
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
Environment=SAGRN_SERVER_URL=http://192.168.1.100:8000
Environment=COLLECTOR_ID=pager1
Environment=PAGER_FREQUENCY=148.1375M
WorkingDirectory=$USER_HOME/sagrn-collector
ExecStart=$USER_HOME/sagrn-collector/venv/bin/python $USER_HOME/sagrn-collector/collector.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE_EOF

echo ""
echo "==================================="
echo "Setup Complete!"
echo "==================================="
echo ""
echo "Next steps:"
echo "1. Edit /etc/systemd/system/sagrn-collector.service"
echo "   - Update SAGRN_SERVER_URL to your server's IP"
echo "   - Update PAGER_FREQUENCY if different"
echo ""
echo "2. Start the service:"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable sagrn-collector"
echo "   sudo systemctl start sagrn-collector"
echo ""
echo "3. Check status:"
echo "   sudo systemctl status sagrn-collector"
echo "   journalctl -u sagrn-collector -f"
echo ""
