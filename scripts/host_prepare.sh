#!/usr/bin/env bash
# SAGRN-SDR Intel NUC Host Preparation Script
# Run once on a fresh Debian NUC to prepare for Docker deployment
#
# Usage: sudo bash host_prepare.sh
set -euo pipefail

echo "=== SAGRN-SDR NUC Host Preparation ==="

# Ensure running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo)."
    exit 1
fi

# 1. Install Docker Engine
echo "[1/5] Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
else
    echo "  Docker already installed: $(docker --version)"
fi

# 2. Install Docker Compose plugin
echo "[2/5] Ensuring Docker Compose plugin..."
apt-get update -qq && apt-get install -y -qq docker-compose-plugin
echo "  $(docker compose version)"

# 3. Create deploy user with limited sudo privileges
echo "[3/5] Creating deploy user..."
if ! id deploy &>/dev/null; then
    useradd -m -s /bin/bash deploy
    echo "  Created user 'deploy'"
else
    echo "  User 'deploy' already exists"
fi

usermod -aG docker deploy

# Setup SSH directory
mkdir -p /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
touch /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

# Limited sudo: only docker and git
cat > /etc/sudoers.d/deploy << 'EOF'
deploy ALL=(ALL) NOPASSWD: /usr/bin/docker, /usr/bin/git
EOF
chmod 440 /etc/sudoers.d/deploy

# 4. RTL-SDR hardware configuration
echo "[4/5] Configuring RTL-SDR..."

# Blacklist DVB-T kernel drivers that conflict with rtl-sdr
cat > /etc/modprobe.d/blacklist-rtlsdr.conf << 'EOF'
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
blacklist dvb_usb_v2
blacklist dvb_core
EOF

# udev rules for non-root RTL-SDR access
cat > /etc/udev/rules.d/20-rtlsdr.rules << 'EOF'
# RTL2832U OEM
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2832", MODE="0666"
# RTL2832U Generic RTL-SDR
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", MODE="0666"
EOF

udevadm control --reload-rules
udevadm trigger

echo "  DVB-T drivers blacklisted, udev rules installed"

# 5. Clone repository and set ownership
echo "[5/5] Setting up project directory..."
PROJECT_DIR=/opt/sagrn-sdr
if [ ! -d "$PROJECT_DIR" ]; then
    git clone https://github.com/steg2011/SAGRN-SDR.git "$PROJECT_DIR"
    echo "  Cloned repository to $PROJECT_DIR"
else
    echo "  Project directory already exists at $PROJECT_DIR"
fi
chown -R deploy:deploy "$PROJECT_DIR"

echo ""
echo "=========================================="
echo "  Host preparation complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Add the deploy user's SSH public key:"
echo "     echo 'ssh-ed25519 AAAA...' >> /home/deploy/.ssh/authorized_keys"
echo ""
echo "  2. Configure GitHub repository secrets:"
echo "     - SSH_PRIVATE_KEY    (deploy user's private key)"
echo "     - NUC_HOST           (this machine's IP or hostname)"
echo "     - POSTGRES_PASSWORD  (choose a strong password)"
echo "     - CLOUDFLARE_TUNNEL_TOKEN (from Cloudflare Zero Trust dashboard)"
echo ""
echo "  3. Push to main branch to trigger deployment, or manually:"
echo "     cd $PROJECT_DIR && docker compose up -d --build"
echo ""
echo "  NOTE: If an RTL-SDR dongle is currently plugged in,"
echo "  unplug and replug it for the new udev rules to take effect."
