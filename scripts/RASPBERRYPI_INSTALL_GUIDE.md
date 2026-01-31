# SAGRN Lightweight - Raspberry Pi Installation Guide

This guide provides step-by-step instructions for installing SAGRN Lightweight on a Raspberry Pi Model 2 B with 1GB of RAM.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Pre-Installation Setup](#pre-installation-setup)
- [Automatic Installation](#automatic-installation)
- [Post-Installation Configuration](#post-installation-configuration)
- [Accessing Your Instance](#accessing-your-instance)
- [Troubleshooting](#troubleshooting)
- [System Management](#system-management)

## Prerequisites

### Hardware Requirements
- **Raspberry Pi 2 Model B** (1GB RAM minimum)
- **16GB Micro SD Card** (recommended 32GB+ for better performance and data retention)
- **Power supply** (5V 2A minimum)
- **Network connection** (Ethernet recommended for stability)

### System Requirements
- **OS**: Raspberry Pi OS Lite (Bullseye or newer) - recommended for minimal resources
- **Free disk space**: ~2GB minimum (1GB for OS + applications, 1GB for database/logs)
- **CPU temperature**: Pi 2 can throttle under load; ensure adequate cooling

### Network Requirements
- Static IP address (recommended) - easier for access and integrations
- Port 80 (HTTP) accessible for web frontend
- Port 8000 (internal) for backend API
- Internet access for external API feeds (CFS, Waze)

## Pre-Installation Setup

### 1. Prepare the Raspberry Pi

1. **Flash Raspberry Pi OS Lite** to Micro SD card:
   - Download from: https://www.raspberrypi.com/software/operating-systems/
   - Use Raspberry Pi Imager tool
   - Select "Raspberry Pi OS Lite (32-bit)" for RPi 2
   - Write to SD card

2. **First boot configuration**:
   ```bash
   sudo raspi-config
   ```
   Configure:
   - System → Boot Options → B2 Wait for Network
   - Interface Options → I2 SSH (enable)
   - Localization → Set timezone and keyboard layout
   - Advanced → Memory Split: set GPU to 16MB (all memory to CPU)
   - Finish and reboot

3. **Update system** (this takes a while):
   ```bash
   sudo apt-get update
   sudo apt-get upgrade -y
   ```

4. **Set static IP address** (optional but recommended):
   Edit `/etc/dhcpcd.conf` and add:
   ```
   interface eth0
   static ip_address=192.168.1.100/24
   static routers=192.168.1.1
   static domain_name_servers=8.8.8.8 1.1.1.1
   ```

### 2. Prepare Application Files

Choose one method:

**Option A: Clone from Git Repository**
```bash
cd /tmp
git clone <your-repository-url> sagrn
sudo cp -r sagrn /opt/sagrn-src
```

**Option B: Transfer via SCP**
```bash
# From your development machine:
scp -r /path/to/SAGRN\ Lightweight pi@192.168.1.100:/tmp/sagrn
# Then on Pi:
sudo cp -r /tmp/sagrn /opt/sagrn-src
```

**Option C: Manual Directory Setup**
```bash
# On the Pi, create structure manually:
sudo mkdir -p /opt/sagrn-src/backend
sudo mkdir -p /opt/sagrn-src/frontend
sudo mkdir -p /opt/sagrn-src/scripts
```

## Automatic Installation

### 1. Download the Installation Script

```bash
# If you cloned the repo:
sudo bash /opt/sagrn-src/scripts/install_raspberrypi.sh

# Or download directly:
sudo bash -c "$(curl -fsSL https://your-domain/install_raspberrypi.sh)"
```

### 2. Monitor Installation Progress

The installation takes 10-20 minutes depending on:
- Your internet connection speed
- Micro SD card speed
- System load

You'll see progress messages with checkmarks (✓) for completed steps.

### 3. Review Installation Summary

At the end, you'll see:
```
=========================================
Installation Complete!
=========================================

Access your SAGRN instance:
  URL: http://192.168.1.100

Backend API: http://192.168.1.100/api
Backend port: 8000 (internal)
Nginx port: 80
```

## Post-Installation Configuration

### 1. Configure Environment Variables

Edit the configuration file:
```bash
sudo nano /opt/sagrn/.env
```

Key settings for Pi 2 (1GB RAM):

```bash
# Keep message retention low
MESSAGE_RETENTION_HOURS=24

# Use single worker (already optimized)
WORKERS=1

# External feeds - customize for your region
CFS_INCIDENTS_XML=https://www.cfs.sa.gov.au/public/feeds/live_incident_feed_text.xml
CFS_CAP_XML=https://www.cfs.sa.gov.au/feeds/cap_xml/cfs_cap_rss.xml

# Enable/disable Waze integration (uses more resources)
# WAZE_API_ENABLED=true
```

### 2. Verify Installation

Check if services are running:
```bash
# Check backend
sudo supervisorctl status sagrn-backend

# Check Nginx
sudo systemctl status nginx

# View logs
sudo tail -f /opt/sagrn/logs/backend.log
```

### 3. Test Access

1. Open browser on same network
2. Go to: `http://<pi-ip-address>`
3. You should see the SAGRN interface

Wait 30-60 seconds for first data load.

## Accessing Your Instance

### Local Network Access
```
http://192.168.1.100        (or your Pi's IP)
http://pi.local              (if mDNS is configured)
```

### Remote Access Options

**Option 1: Port Forwarding (Simple but less secure)**
- Forward port 80 on router to Pi's port 80
- Access via: `http://your-public-ip`

**Option 2: VPN (Recommended)**
- Install WireGuard or OpenVPN on Pi
- Access only when connected to VPN

**Option 3: Reverse Proxy (Advanced)**
- Set up reverse proxy on a remote server
- Use SSL/TLS encryption

## Troubleshooting

### Issue: Slow or Unresponsive Interface

**Cause**: Memory exhaustion (1GB is tight)

**Solutions**:
1. Check memory usage:
   ```bash
   free -h
   ```

2. Reduce data retention:
   ```bash
   # Edit .env
   MESSAGE_RETENTION_HOURS=12  # Even shorter
   ```

3. Restart backend:
   ```bash
   sudo supervisorctl restart sagrn-backend
   ```

4. Monitor swap usage:
   ```bash
   vmstat 1 10
   ```

### Issue: Backend Won't Start

**Check logs**:
```bash
sudo tail -f /opt/sagrn/logs/backend_error.log
```

**Common errors**:

1. **"Address already in use"**
   ```bash
   # Kill process on port 8000
   sudo lsof -i :8000
   sudo kill -9 <PID>
   sudo supervisorctl restart sagrn-backend
   ```

2. **"Database locked"**
   - SQLite limitation with multiple processes
   - Already handled (WORKERS=1), but may occur if multiple connections
   - Restart: `sudo supervisorctl restart sagrn-backend`

3. **"Permission denied"**
   ```bash
   # Fix permissions
   sudo chown -R sagrn:sagrn /opt/sagrn
   sudo supervisorctl restart sagrn-backend
   ```

### Issue: Frontend Won't Load

**Check Nginx**:
```bash
sudo nginx -t              # Check config syntax
sudo systemctl status nginx
sudo tail -f /var/log/nginx/error.log
```

**Rebuild frontend** (if needed):
```bash
cd /opt/sagrn/frontend
npm run build
sudo systemctl reload nginx
```

### Issue: External API Feeds Not Updating

**Check logs**:
```bash
sudo journalctl -u sagrn -n 50
```

**Common causes**:
- Network connectivity issue
- Invalid feed URL
- API rate limiting

**Test connectivity**:
```bash
curl -I https://www.cfs.sa.gov.au/public/feeds/live_incident_feed_text.xml
```

### Issue: High CPU Temperature

The Pi 2 can throttle under sustained load.

**Solutions**:
1. Add heatsink to CPU
2. Improve airflow/cooling
3. Reduce polling frequencies in config (increase interval times)
4. Run during off-peak hours

### Issue: Disk Full

**Check disk space**:
```bash
df -h
```

**Clear logs** (if safe):
```bash
sudo truncate -s 0 /opt/sagrn/logs/*.log
sudo journalctl --vacuum=100M
```

**Reduce data retention**:
```bash
# Edit .env to shorter duration
MESSAGE_RETENTION_HOURS=12
sudo supervisorctl restart sagrn-backend
```

## System Management

### Viewing Logs

```bash
# Backend application logs
sudo tail -f /opt/sagrn/logs/backend.log

# Backend errors
sudo tail -f /opt/sagrn/logs/backend_error.log

# Supervisor logs
sudo supervisorctl tail sagrn-backend

# Nginx access logs
sudo tail -f /var/log/nginx/access.log

# Nginx error logs
sudo tail -f /var/log/nginx/error.log

# System journal
sudo journalctl -u sagrn -n 50 -f
```

### Restarting Services

```bash
# Restart backend
sudo supervisorctl restart sagrn-backend

# Restart Nginx
sudo systemctl restart nginx

# Restart all (complete restart)
sudo reboot
```

### Monitoring System Health

```bash
# Real-time monitoring
htop

# Memory usage
free -h

# Disk usage
df -h

# CPU temperature
vcgencmd measure_temp

# Network
ifstat
```

### Updating the Application

When you have code changes:

```bash
# Pull latest code
cd /opt/sagrn
sudo git pull origin main

# Rebuild frontend (if frontend changed)
cd frontend
npm install
npm run build
sudo systemctl reload nginx

# Restart backend (if backend changed)
sudo supervisorctl restart sagrn-backend
```

### Backup Database

```bash
# Manual backup
sudo cp /opt/sagrn/data/sagrn.db /opt/sagrn/data/sagrn.db.backup

# Automated daily backup (add to crontab)
sudo crontab -e
# Add: 0 2 * * * cp /opt/sagrn/data/sagrn.db /opt/sagrn/backups/sagrn-$(date +\%Y\%m\%d).db
```

### Enable Remote SSH Access

**Security Warning**: Only if needed; use SSH keys, not passwords.

```bash
# SSH is enabled by raspi-config
# Set SSH key authentication:
ssh-copy-id -i ~/.ssh/id_rsa.pub pi@192.168.1.100

# Disable password auth (in /etc/ssh/sshd_config):
# PasswordAuthentication no
# PubkeyAuthentication yes

sudo systemctl restart ssh
```

## Performance Optimization Tips

### For 1GB RAM Raspberry Pi 2:

1. **Disable unnecessary services**:
   ```bash
   sudo systemctl disable bluetooth
   sudo systemctl disable avahi-daemon
   ```

2. **Reduce GPU memory**:
   Already done in raspi-config (16MB)

3. **Use lightweight alternatives**:
   - Nginx instead of Apache (already done)
   - SQLite instead of PostgreSQL (already done)

4. **Optimize database**:
   ```bash
   # Periodic maintenance
   sqlite3 /opt/sagrn/data/sagrn.db "VACUUM;"
   ```

5. **Monitor and adjust**:
   - Watch `free` and `vmstat` output
   - Increase swap if needed (already configured at 1GB)
   - Adjust MESSAGE_RETENTION_HOURS based on disk space

## Support and Further Help

For issues not covered here:

1. **Check application logs** - Most issues will have error messages
2. **Review Raspberry Pi documentation** - https://www.raspberrypi.com/documentation/
3. **Monitor system resources** - Use `htop` and `vmstat` to identify bottlenecks
4. **Test external connectivity** - Use `curl` to verify API access

## Next Steps

After successful installation:

1. Configure your external API feeds in `.env`
2. Set up remote access if needed (VPN recommended)
3. Configure log rotation and backups
4. Monitor performance and adjust settings based on load
5. Plan capacity - if growth exceeds Pi 2 capabilities, consider Pi 4 or cloud deployment

---

**Last Updated**: 2026-01-31
**Compatible With**: SAGRN Lightweight v2.0+
**Tested On**: Raspberry Pi 2 Model B, 1GB RAM, Raspberry Pi OS Lite
