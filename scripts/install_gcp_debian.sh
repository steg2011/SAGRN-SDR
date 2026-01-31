#!/bin/bash
#
# SAGRN SDR Monitor - GCP Debian Installation Script
# Lightweight edition optimized for Google Cloud free tier e2-micro instance
#
# Usage: sudo ./install_gcp_debian.sh
#
# This script will:
# 1. Install system dependencies (Python 3.11, Node.js 20)
# 2. Create application user and directory
# 3. Set up Python virtual environment
# 4. Install Python dependencies
# 5. Build the React frontend
# 6. Create systemd service
# 7. Configure firewall
# 8. Start the service
#

set -e  # Exit on error

# Configuration
APP_NAME="sagrn-sdr"
APP_USER="sagrn"
APP_DIR="/opt/sagrn-sdr"
REPO_URL="https://github.com/steg2011/SAGRN-SDR.git"
BRANCH="main"
PORT=8000

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (use sudo)"
    exit 1
fi

log_info "Starting SAGRN SDR Monitor installation for GCP Debian..."

# =============================================================================
# Step 1: Update system and install dependencies
# =============================================================================
log_info "Updating system packages..."
apt-get update
apt-get upgrade -y

log_info "Installing system dependencies..."
apt-get install -y \
    curl \
    git \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    libffi-dev \
    libssl-dev

# Install Node.js 20.x (LTS) for building frontend
log_info "Installing Node.js 20.x..."
if ! command -v node &> /dev/null || [[ $(node -v | cut -d'.' -f1 | tr -d 'v') -lt 20 ]]; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi

log_info "Node.js version: $(node -v)"
log_info "npm version: $(npm -v)"
log_info "Python version: $(python3 --version)"

# =============================================================================
# Step 2: Create application user and directory
# =============================================================================
log_info "Creating application user and directory..."

# Create user if doesn't exist
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --shell /bin/bash --home-dir "$APP_DIR" "$APP_USER"
fi

# Create application directory
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/data"

# =============================================================================
# Step 3: Clone or update repository
# =============================================================================
log_info "Cloning repository..."

if [ -d "$APP_DIR/.git" ]; then
    log_info "Repository exists, pulling latest changes..."
    cd "$APP_DIR"
    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
else
    # Clone fresh
    cd /opt
    rm -rf "$APP_DIR"
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"

# =============================================================================
# Step 4: Set up Python virtual environment
# =============================================================================
log_info "Setting up Python virtual environment..."

cd "$APP_DIR/backend"

# Create virtual environment
python3 -m venv venv

# Activate and install dependencies
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

deactivate

# =============================================================================
# Step 5: Create environment file
# =============================================================================
log_info "Creating environment configuration..."

if [ ! -f "$APP_DIR/backend/.env" ]; then
    cat > "$APP_DIR/backend/.env" << EOF
# SAGRN SDR Monitor Configuration
DATABASE_URL=sqlite+aiosqlite:///$APP_DIR/data/sagrn.db
MESSAGE_RETENTION_HOURS=24
HOST=0.0.0.0
PORT=$PORT
WORKERS=1
EOF
fi

# =============================================================================
# Step 6: Verify pre-built frontend
# =============================================================================
log_info "Verifying pre-built frontend..."

cd "$APP_DIR/frontend"

if [ ! -d "build" ]; then
    log_error "Pre-built frontend not found!"
    log_error "This installation requires pre-built artifacts from the repository."
    log_error "Clone from: https://github.com/steg2011/SAGRN-SDR"
    exit 1
fi

if [ ! -f "build/index.html" ]; then
    log_error "Pre-built frontend is incomplete"
    exit 1
fi

log_info "✓ Frontend ready (using pre-built artifacts)"

# =============================================================================
# Step 7: Set ownership and permissions
# =============================================================================
log_info "Setting ownership and permissions..."

chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod -R 755 "$APP_DIR"
chmod 700 "$APP_DIR/data"

# =============================================================================
# Step 8: Create systemd service
# =============================================================================
log_info "Creating systemd service..."

cat > /etc/systemd/system/sagrn-sdr.service << EOF
[Unit]
Description=SAGRN SDR Monitor - Emergency Services Pager Monitor
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR/backend
Environment="PATH=$APP_DIR/backend/venv/bin"
ExecStart=$APP_DIR/backend/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=10

# Resource limits for GCP free tier (e2-micro: 1GB RAM, 0.25 vCPU)
MemoryMax=512M
CPUQuota=50%

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR/data

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

# =============================================================================
# Step 9: Configure firewall (if ufw is available)
# =============================================================================
log_info "Configuring firewall..."

if command -v ufw &> /dev/null; then
    ufw allow $PORT/tcp comment 'SAGRN SDR Monitor'
    log_info "UFW rule added for port $PORT"
else
    log_warn "UFW not installed. Make sure to configure GCP firewall rules to allow port $PORT"
fi

# =============================================================================
# Step 10: Start and enable service
# =============================================================================
log_info "Starting SAGRN SDR Monitor service..."

systemctl enable sagrn-sdr
systemctl start sagrn-sdr

# Wait for service to start
sleep 3

# Check status
if systemctl is-active --quiet sagrn-sdr; then
    log_info "Service started successfully!"
else
    log_error "Service failed to start. Check logs with: journalctl -u sagrn-sdr -f"
    systemctl status sagrn-sdr
    exit 1
fi

# =============================================================================
# Step 11: Print summary
# =============================================================================
echo ""
echo "=============================================="
echo -e "${GREEN}SAGRN SDR Monitor Installation Complete!${NC}"
echo "=============================================="
echo ""
echo "Service Status:"
systemctl status sagrn-sdr --no-pager | head -5
echo ""
echo "Access the web interface at:"
echo "  http://$(hostname -I | awk '{print $1}'):$PORT"
echo ""
echo "Useful commands:"
echo "  View logs:     journalctl -u sagrn-sdr -f"
echo "  Restart:       systemctl restart sagrn-sdr"
echo "  Stop:          systemctl stop sagrn-sdr"
echo "  Status:        systemctl status sagrn-sdr"
echo ""
echo "Data directory: $APP_DIR/data"
echo ""
echo "IMPORTANT: Configure your Raspberry Pi collector to send messages to:"
echo "  http://YOUR_GCP_EXTERNAL_IP:$PORT/api/collector/message"
echo ""
echo "GCP Firewall: Make sure to create a firewall rule allowing TCP port $PORT"
echo "  gcloud compute firewall-rules create sagrn-web --allow tcp:$PORT"
echo ""
