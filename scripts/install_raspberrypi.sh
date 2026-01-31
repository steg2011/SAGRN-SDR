#!/bin/bash
#
# SAGRN Lightweight Installation Script for Raspberry Pi 2 B
# This script sets up both backend services and web frontend on RPi with 1GB RAM
#
# Usage: sudo bash install_raspberrypi.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="${APP_DIR:-/opt/sagrn}"
APP_USER="${APP_USER:-sagrn}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
DB_PATH="${APP_DIR}/data/sagrn.db"

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

log_info "========================================="
log_info "SAGRN Lightweight - Raspberry Pi Setup"
log_info "========================================="

check_root

# System information
log_info "Collecting system information..."
RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
RAM_MB=$((RAM_KB / 1024))
log_info "Detected RAM: ${RAM_MB}MB"

if [[ $RAM_MB -lt 800 ]]; then
    log_warn "Low memory detected. This may cause issues during Node.js build."
    log_warn "Consider enabling swap or building frontend on another machine."
fi

# Step 1: Update system packages
log_info "Step 1: Updating system packages..."
apt-get update
apt-get upgrade -y
apt-get install -y \
    build-essential \
    curl \
    wget \
    git \
    python3 \
    python3-dev \
    python3-venv \
    python3-pip \
    sqlite3 \
    nginx \
    supervisor \
    htop

log_info "✓ System packages updated"

# Step 2: Create application user and directories
log_info "Step 2: Setting up application user and directories..."
if ! id -u "$APP_USER" > /dev/null 2>&1; then
    useradd -r -s /bin/bash -d "$APP_DIR" "$APP_USER"
    log_info "Created user: $APP_USER"
else
    log_warn "User $APP_USER already exists"
fi

mkdir -p "$APP_DIR"/{data,logs,venv,backend,frontend}
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
log_info "✓ Directories created"

# Step 3: Install Node.js (LTS version compatible with RPi 2)
log_info "Step 3: Installing Node.js..."
if ! command -v node &> /dev/null; then
    # Install NodeSource repository for ARMv7 (RPi 2)
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
    apt-get install -y nodejs
    log_info "✓ Node.js installed"
else
    NODE_VERSION=$(node -v)
    log_warn "Node.js already installed: $NODE_VERSION"
fi

# Enable npm to use less memory during builds
npm config set memory 256

# Step 4: Setup backend
log_info "Step 4: Setting up Python backend..."
cp -r /root/sagrn-backend "$APP_DIR/backend" 2>/dev/null || {
    log_warn "Backend directory not found at /root/sagrn-backend"
    log_warn "Assuming backend is already in place or will be copied manually"
}

cd "$APP_DIR/backend"

# Create Python virtual environment
log_info "Creating Python virtual environment..."
python3 -m venv "$APP_DIR/venv"
source "$APP_DIR/venv/bin/activate"

# Install Python dependencies
log_info "Installing Python dependencies (this may take a few minutes)..."
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

log_info "✓ Backend setup complete"

# Step 5: Verify pre-built frontend
log_info "Step 5: Verifying pre-built frontend..."

cd "$APP_DIR/frontend"

if [ ! -d "build" ]; then
    log_error "Pre-built frontend not found!"
    log_error "This installation requires pre-built artifacts."
    log_error "Ensure you're deploying from the latest commit that includes frontend/build/"
    exit 1
fi

# Verify build has required files
if [ ! -f "build/index.html" ]; then
    log_error "Pre-built frontend is incomplete (missing index.html)"
    exit 1
fi

log_info "✓ Frontend ready (using pre-built artifacts)"
log_info "Skipped build process - saving 15-30 minutes and 800MB RAM"

# Step 6: Create .env file for backend
log_info "Step 6: Creating backend configuration..."
ENV_FILE="$APP_DIR/backend/.env"

cat > "$ENV_FILE" << 'EOF'
# SAGRN Lightweight - Raspberry Pi Configuration

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/sagrn.db

# Server configuration (optimized for 1GB RAM)
HOST=0.0.0.0
PORT=8000
WORKERS=1

# Reduce data retention for limited storage
MESSAGE_RETENTION_HOURS=24

# External API feeds
CFS_INCIDENTS_XML=https://www.cfs.sa.gov.au/public/feeds/live_incident_feed_text.xml
CFS_CAP_XML=https://www.cfs.sa.gov.au/feeds/cap_xml/cfs_cap_rss.xml

# Logging
LOG_LEVEL=info

# Optional: Waze integration
# WAZE_API_ENABLED=true
# WAZE_BOUNDS=-37.5,-36.5,140.5,141.5
EOF

chown "$APP_USER:$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"
log_info "✓ Configuration file created: $ENV_FILE"
log_info "  Edit this file to customize settings"

# Step 7: Setup Nginx reverse proxy
log_info "Step 7: Configuring Nginx reverse proxy..."

NGINX_CONF="/etc/nginx/sites-available/sagrn"
cat > "$NGINX_CONF" << EOF
upstream sagrn_backend {
    server 127.0.0.1:$BACKEND_PORT;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;

    server_name _;
    client_max_body_size 10M;

    # Serve static frontend files
    location / {
        root $APP_DIR/frontend/build;
        try_files \$uri /index.html;
    }

    # Proxy API requests to backend
    location /api/ {
        proxy_pass http://sagrn_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Proxy Server-Sent Events (SSE)
    location /api/events {
        proxy_pass http://sagrn_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Host \$host;
    }
}
EOF

# Enable the site
ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/sagrn 2>/dev/null || true
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# Test and reload Nginx
nginx -t
systemctl reload nginx
log_info "✓ Nginx configured"

# Step 8: Setup Supervisor for backend service
log_info "Step 8: Creating Supervisor configuration for backend..."

SUPERVISOR_CONF="/etc/supervisor/conf.d/sagrn-backend.conf"
cat > "$SUPERVISOR_CONF" << EOF
[program:sagrn-backend]
directory=$APP_DIR/backend
command=$APP_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --workers 1
user=$APP_USER
autostart=true
autorestart=true
stdout_logfile=$APP_DIR/logs/backend.log
stderr_logfile=$APP_DIR/logs/backend_error.log
environment=PATH="$APP_DIR/venv/bin"
EOF

log_info "✓ Supervisor configuration created"

# Initialize Supervisor
systemctl restart supervisor
supervisorctl reread
supervisorctl update
log_info "✓ Backend service started"

# Step 9: Setup systemd service for automatic startup
log_info "Step 9: Creating systemd service..."

SYSTEMD_SERVICE="/etc/systemd/system/sagrn.service"
cat > "$SYSTEMD_SERVICE" << EOF
[Unit]
Description=SAGRN Lightweight - Emergency Incident Monitoring
After=network.target

[Service]
Type=notify
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=/bin/bash -c 'source $APP_DIR/venv/bin/activate && exec $APP_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --workers 1'
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable sagrn
log_info "✓ Systemd service created and enabled"

# Step 10: Setup log rotation
log_info "Step 10: Configuring log rotation..."

LOGROTATE_CONF="/etc/logrotate.d/sagrn"
cat > "$LOGROTATE_CONF" << EOF
$APP_DIR/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 $APP_USER $APP_USER
    sharedscripts
    postrotate
        supervisorctl restart sagrn-backend > /dev/null 2>&1 || true
    endscript
}
EOF

log_info "✓ Log rotation configured"

# Step 11: Performance optimization
log_info "Step 11: Optimizing system for low-memory operation..."

# Note: Swap still created for backend operations and future flexibility
# Frontend build no longer performed on-device (uses pre-built artifacts)

# Increase swap (recommended for 1GB RPi)
if ! grep -q "/swapfile" /etc/fstab; then
    log_info "Creating 1GB swap file..."
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo "/swapfile none swap sw 0 0" >> /etc/fstab
    log_info "✓ Swap file created"
else
    log_warn "Swap file already configured"
fi

# Optimize system limits
cat >> /etc/sysctl.conf << EOF

# SAGRN optimization
vm.swappiness=10
vm.dirty_writeback_centisecs=500
fs.file-max=65535
EOF

sysctl -p > /dev/null

log_info "✓ System optimizations applied"

# Step 12: Initialize database
log_info "Step 12: Initializing database..."
cd "$APP_DIR/backend"
source "$APP_DIR/venv/bin/activate"
# Database will be created automatically on first run
log_info "✓ Database ready (will be created on first backend run)"

# Step 13: Final checks
log_info "Step 13: Running final checks..."

log_info "Checking services..."
systemctl is-active --quiet nginx && log_info "✓ Nginx is running" || log_error "Nginx failed to start"
supervisorctl status sagrn-backend | grep -q RUNNING && log_info "✓ Backend service is running" || log_warn "Backend service not yet running"

# Display status
log_info ""
log_info "========================================="
log_info "Installation Complete!"
log_info "========================================="
log_info ""
log_info "Access your SAGRN instance:"
log_info "  URL: http://$(hostname -I | awk '{print $1}')"
log_info ""
log_info "Backend API: http://$(hostname -I | awk '{print $1}')/api"
log_info "Backend port: $BACKEND_PORT (internal)"
log_info "Nginx port: 80"
log_info ""
log_info "Installation details:"
log_info "  App directory: $APP_DIR"
log_info "  App user: $APP_USER"
log_info "  Configuration: $ENV_FILE"
log_info "  Backend logs: $APP_DIR/logs/backend.log"
log_info "  Nginx logs: /var/log/nginx/"
log_info ""
log_info "Useful commands:"
log_info "  View backend logs: tail -f $APP_DIR/logs/backend.log"
log_info "  Check backend status: supervisorctl status sagrn-backend"
log_info "  Restart backend: supervisorctl restart sagrn-backend"
log_info "  Check system status: systemctl status sagrn"
log_info "  View Nginx logs: tail -f /var/log/nginx/error.log"
log_info ""
log_info "Next steps:"
log_info "  1. Edit $ENV_FILE to configure external API feeds"
log_info "  2. Check logs to ensure backend started correctly"
log_info "  3. Open browser to http://$(hostname -I | awk '{print $1}') to test"
log_info ""
log_info "Reboot to ensure everything starts automatically:"
log_info "  sudo reboot"
log_info ""
log_info "========================================="
