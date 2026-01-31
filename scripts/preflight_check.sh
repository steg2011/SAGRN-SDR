#!/bin/bash
#
# SAGRN Lightweight - Pre-flight Check Script for Raspberry Pi
# Run this before installation to verify system compatibility
#
# Usage: sudo bash preflight_check.sh
#

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((ERRORS++))
}

print_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    check_fail "This script must be run as root (use: sudo bash preflight_check.sh)"
    exit 1
fi

print_header "SAGRN Lightweight - Pre-flight Check"

# 1. Check Hardware
print_header "Hardware Verification"

# Check if Raspberry Pi
if grep -q "Raspberry Pi" /proc/cpuinfo; then
    MODEL=$(grep "Model" /proc/cpuinfo | head -1 | cut -d: -f2 | xargs)
    check_pass "Raspberry Pi detected: $MODEL"
else
    check_warn "Not a Raspberry Pi - some optimizations may not apply"
fi

# Check CPU cores
CORES=$(nproc)
check_pass "CPU cores: $CORES"

# Check RAM
RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
RAM_MB=$((RAM_KB / 1024))
RAM_GB=$(printf "%.2f" $(echo "scale=2; $RAM_KB / 1024 / 1024" | bc))

if [[ $RAM_MB -ge 1024 ]]; then
    check_pass "RAM: ${RAM_GB}GB (Sufficient)"
elif [[ $RAM_MB -ge 800 ]]; then
    check_warn "RAM: ${RAM_GB}GB (Minimum - may have performance issues)"
else
    check_fail "RAM: ${RAM_GB}GB (Insufficient - need at least 800MB)"
fi

# Check available disk space
DISK_AVAILABLE=$(df /opt 2>/dev/null | tail -1 | awk '{print $4}')
if [ -z "$DISK_AVAILABLE" ]; then
    DISK_AVAILABLE=$(df / | tail -1 | awk '{print $4}')
fi
DISK_GB=$((DISK_AVAILABLE / 1024 / 1024))

if [[ $DISK_GB -ge 2 ]]; then
    check_pass "Available disk space: ${DISK_GB}GB (Sufficient)"
elif [[ $DISK_GB -ge 1 ]]; then
    check_warn "Available disk space: ${DISK_GB}GB (Tight - limited data retention)"
else
    check_fail "Available disk space: ${DISK_GB}GB (Insufficient - need at least 1GB)"
fi

# Check temperature
TEMP=$(vcgencmd measure_temp 2>/dev/null | grep -oP '\d+\.\d+')
if [ -n "$TEMP" ]; then
    TEMP_INT=$(echo $TEMP | cut -d. -f1)
    if [[ $TEMP_INT -lt 50 ]]; then
        check_pass "CPU temperature: ${TEMP}°C (Normal)"
    elif [[ $TEMP_INT -lt 70 ]]; then
        check_warn "CPU temperature: ${TEMP}°C (Warm - ensure cooling)"
    else
        check_fail "CPU temperature: ${TEMP}°C (Hot - add heatsink)"
    fi
else
    check_warn "Could not read CPU temperature"
fi

# 2. Check Software Requirements
print_header "Software Requirements"

# Check OS
if grep -q "Raspberry Pi OS" /etc/os-release; then
    check_pass "Operating System: Raspberry Pi OS detected"
else
    check_warn "Not Raspberry Pi OS - some tools may not be available"
fi

# Check Python
if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    check_pass "Python 3: $PY_VERSION found"
else
    check_fail "Python 3: Not installed (required)"
fi

# Check pip
if command -v pip3 &> /dev/null; then
    check_pass "pip3: Found"
else
    check_warn "pip3: Not found (will be installed during setup)"
fi

# Check Node.js
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    check_pass "Node.js: $NODE_VERSION found"
else
    check_warn "Node.js: Not installed (will be installed during setup)"
fi

# Check npm
if command -v npm &> /dev/null; then
    NPM_VERSION=$(npm --version)
    check_pass "npm: $NPM_VERSION found"
else
    check_warn "npm: Not installed (will be installed with Node.js)"
fi

# Check Git
if command -v git &> /dev/null; then
    check_pass "Git: Found"
else
    check_warn "Git: Not installed (optional)"
fi

# Check Nginx
if command -v nginx &> /dev/null; then
    check_warn "Nginx: Already installed (will be reconfigured)"
else
    check_pass "Nginx: Not installed (will be installed)"
fi

# Check Supervisor
if command -v supervisorctl &> /dev/null; then
    check_warn "Supervisor: Already installed (will be reconfigured)"
else
    check_pass "Supervisor: Not installed (will be installed)"
fi

# 3. Check Network
print_header "Network Configuration"

# Check internet connectivity
if timeout 2 ping -c 1 8.8.8.8 &> /dev/null; then
    check_pass "Internet connectivity: Working"
else
    check_fail "Internet connectivity: Failed (required for installation)"
fi

# Check DNS
if nslookup google.com &> /dev/null; then
    check_pass "DNS resolution: Working"
else
    check_fail "DNS resolution: Failed"
fi

# Check IP address
IP_ADDR=$(hostname -I | awk '{print $1}')
if [ -n "$IP_ADDR" ]; then
    check_pass "IP address: $IP_ADDR"
else
    check_fail "IP address: Could not determine"
fi

# Check if static IP (not DHCP)
if grep -q "static ip_address" /etc/dhcpcd.conf 2>/dev/null; then
    check_pass "Network: Static IP configured (good)"
else
    check_warn "Network: DHCP enabled (consider setting static IP)"
fi

# 4. Check File System
print_header "File System"

# Check root filesystem type
FS_TYPE=$(df / | tail -1 | awk '{print $1}')
if [[ "$FS_TYPE" == *"ext4"* ]] || [[ "$FS_TYPE" == *"btrfs"* ]]; then
    check_pass "Root filesystem: Suitable for SQLite"
else
    check_warn "Root filesystem: $FS_TYPE (may affect database performance)"
fi

# Check /tmp free space
TMP_SPACE=$(df /tmp | tail -1 | awk '{print $4}')
TMP_GB=$((TMP_SPACE / 1024 / 1024))
if [[ $TMP_GB -ge 100 ]]; then
    check_pass "/tmp free space: ${TMP_GB}GB"
else
    check_warn "/tmp free space: ${TMP_GB}GB (low - build may struggle)"
fi

# 5. Check Permissions
print_header "System Permissions"

# Check if can create directories
TEST_DIR="/opt/sagrn_test_$$"
if mkdir -p "$TEST_DIR" 2>/dev/null; then
    rmdir "$TEST_DIR"
    check_pass "Can create directories in /opt"
else
    check_fail "Cannot create directories in /opt (permission issue)"
fi

# Check sudo access
if sudo -n true 2>/dev/null; then
    check_pass "sudo access without password configured"
else
    check_warn "sudo password will be required during installation"
fi

# 6. Check Ports
print_header "Network Ports"

# Check port 80
if ! lsof -Pi :80 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    check_pass "Port 80: Available (HTTP web frontend)"
else
    check_warn "Port 80: In use (will be replaced)"
fi

# Check port 8000
if ! lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    check_pass "Port 8000: Available (Backend API)"
else
    check_warn "Port 8000: In use (will be replaced)"
fi

# 7. Check User Account
print_header "User Account"

if id "sagrn" &>/dev/null; then
    check_warn "User 'sagrn' already exists (will be reused)"
else
    check_pass "User 'sagrn' does not exist (will be created)"
fi

# Summary
print_header "Summary"

echo ""
if [[ $ERRORS -eq 0 && $WARNINGS -eq 0 ]]; then
    echo -e "${GREEN}✓ All checks passed! System is ready for installation.${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Copy SAGRN source files to /opt/sagrn-src/ (if not already done)"
    echo "  2. Run: sudo bash /path/to/install_raspberrypi.sh"
    echo ""
    exit 0
elif [[ $ERRORS -eq 0 ]]; then
    echo -e "${YELLOW}⚠ $WARNINGS warning(s) found - installation should proceed but may have issues${NC}"
    echo ""
    echo "Review warnings above and address if possible:"
    echo "  - Low RAM: Close background processes or add swap"
    echo "  - Low disk: Consider expanding partition or cleaning up"
    echo "  - Warm CPU: Add heatsink or improve cooling"
    echo ""
    read -p "Continue with installation anyway? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Proceeding to installation..."
        exit 0
    else
        exit 1
    fi
else
    echo -e "${RED}✗ $ERRORS critical error(s) found - installation cannot proceed${NC}"
    echo ""
    echo "Please fix the above errors before installing:"
    echo "  - Install Python 3"
    echo "  - Ensure internet connectivity"
    echo "  - Free up at least 1GB of disk space"
    echo "  - Check IP address configuration"
    echo ""
    exit 1
fi
