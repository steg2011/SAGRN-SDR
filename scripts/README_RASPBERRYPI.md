# SAGRN Lightweight - Raspberry Pi Installation

Complete installation and deployment guide for running SAGRN Lightweight on a Raspberry Pi Model 2 B with 1GB RAM.

## Overview

This directory contains everything you need to deploy SAGRN (Incident Monitoring System) on a Raspberry Pi 2. The installation includes:

- **Backend**: Python FastAPI with SQLite database
- **Frontend**: React web interface
- **Services**: Nginx reverse proxy, Supervisor service management
- **Optimization**: Tuned for 1GB RAM with swap, single worker processes, lightweight database retention

## Files in This Directory

| File | Purpose |
|------|---------|
| `install_raspberrypi.sh` | **Main installation script** - automated setup of entire system |
| `preflight_check.sh` | Pre-installation validation - checks hardware/software requirements |
| `RASPBERRYPI_INSTALL_GUIDE.md` | **Comprehensive guide** - detailed setup and configuration instructions |
| `QUICK_REFERENCE.md` | **Quick commands** - common troubleshooting and management commands |
| `README_RASPBERRYPI.md` | This file - overview and getting started |

## Quick Start

### 1. Prepare Raspberry Pi (5-10 minutes)

```bash
# Flash Raspberry Pi OS Lite to SD card
# https://www.raspberrypi.com/software/

# Boot and connect to network
# On Pi, enable SSH and update system:
sudo raspi-config
# → Interface Options → SSH → Enable
# → System → Boot Options → Wait for Network
# → Advanced → GPU Memory → 16MB
# → Finish and reboot

sudo apt-get update
sudo apt-get upgrade -y
```

### 2. Prepare Application Files

Choose one method:

**Clone from Git**:
```bash
cd /tmp
git clone <your-repo-url> sagrn
sudo cp -r sagrn /opt/sagrn-src
```

**Or copy via SCP** from your development machine:
```bash
scp -r /path/to/SAGRN\ Lightweight pi@<pi-ip>:/tmp/sagrn
# Then on Pi:
sudo cp -r /tmp/sagrn /opt/sagrn-src
```

### 3. Run Installation (10-20 minutes)

```bash
# Run pre-flight checks first (optional but recommended)
sudo bash /opt/sagrn-src/scripts/preflight_check.sh

# Run main installation
sudo bash /opt/sagrn-src/scripts/install_raspberrypi.sh
```

### 4. Access Your Instance

After installation completes:

```bash
# Find your Pi's IP address
hostname -I

# Open in browser
http://<pi-ip>
# Example: http://192.168.1.100
```

Wait 30-60 seconds for first data load from external APIs.

## System Architecture

```
User Browser
    ↓
Nginx (Port 80)
    ├→ Static React frontend from /build
    └→ API requests proxied to backend
         ↓
FastAPI Backend (Port 8000, single worker)
    ├→ SQLite Database (/data/sagrn.db)
    ├→ Background tasks (CFS/Waze updates)
    └→ Server-Sent Events (real-time updates)
```

## Key Optimizations for 1GB RAM

1. **Single Worker**: FastAPI runs with `WORKERS=1` to minimize memory
2. **Short Data Retention**: `MESSAGE_RETENTION_HOURS=24` keeps database small
3. **Swap Space**: Automated 1GB swap file during installation
4. **Lightweight OS**: Uses Nginx (not Apache) and SQLite (not PostgreSQL)
5. **Service Management**: Supervisor manages backend, auto-restart on failure

## Directory Structure After Installation

```
/opt/sagrn/
├── backend/              # FastAPI application
│   ├── app/
│   ├── requirements.txt
│   ├── run.py
│   └── .env             # Configuration file (edit for API feeds)
├── frontend/            # React application
│   ├── src/
│   ├── build/          # Production build
│   └── package.json
├── data/               # Database
│   └── sagrn.db        # SQLite database
├── logs/               # Application logs
│   ├── backend.log
│   └── backend_error.log
└── venv/               # Python virtual environment
```

## Important Files to Configure

After installation, edit this file:

```bash
sudo nano /opt/sagrn/.env
```

Key settings:
- `CFS_INCIDENTS_XML` - Feed URL for incident data
- `MESSAGE_RETENTION_HOURS` - How long to keep data (default: 24 hours)
- `WORKERS` - Number of worker processes (keep at 1)
- `LOG_LEVEL` - Logging verbosity (info/warn/debug)

## Troubleshooting

### Quick Diagnosis
```bash
# Check if services are running
sudo supervisorctl status
sudo systemctl status nginx

# View logs
sudo tail -f /opt/sagrn/logs/backend.log

# Check resources
free -h
df -h
```

### Common Issues

| Problem | Solution |
|---------|----------|
| **Slow/unresponsive** | Check `free -h` for memory; restart with `sudo supervisorctl restart sagrn-backend` |
| **Backend won't start** | Check `/opt/sagrn/logs/backend_error.log` for errors |
| **Frontend won't load** | Verify frontend built: `ls /opt/sagrn/frontend/build/` |
| **High temperature** | Add heatsink; reduce polling frequency in `.env` |
| **Disk full** | Reduce `MESSAGE_RETENTION_HOURS` or clear old logs |

For detailed troubleshooting, see **QUICK_REFERENCE.md** or **RASPBERRYPI_INSTALL_GUIDE.md**.

## Daily Operations

### Start/Stop Services
```bash
# Stop backend
sudo supervisorctl stop sagrn-backend

# Start backend
sudo supervisorctl start sagrn-backend

# Restart everything
sudo reboot
```

### View Status
```bash
# Service status
sudo supervisorctl status

# System health
htop

# Recent logs
sudo tail -50 /opt/sagrn/logs/backend.log
```

### Backup Data
```bash
# Backup database
sudo cp /opt/sagrn/data/sagrn.db /opt/sagrn/data/sagrn.db.backup

# Restore if needed
sudo cp /opt/sagrn/data/sagrn.db.backup /opt/sagrn/data/sagrn.db
sudo supervisorctl restart sagrn-backend
```

## Advanced Configuration

### Enable Remote Access (VPN Recommended)

For security, use VPN instead of direct exposure. Example with WireGuard:

```bash
# Install WireGuard
sudo apt-get install wireguard wireguard-tools

# Configure (beyond scope of this guide)
# Then access SAGRN only when connected to VPN
```

### Increase Data Retention

If you have more disk space:
```bash
# Edit .env
MESSAGE_RETENTION_HOURS=72  # Keep 3 days instead of 1

# Restart backend
sudo supervisorctl restart sagrn-backend
```

### Monitor Performance

```bash
# Real-time monitoring
htop

# Check database size
du -sh /opt/sagrn/data/sagrn.db

# Monitor API response times (tail logs)
sudo grep "GET /api" /var/log/nginx/access.log
```

### Update Application

When you have code changes:

```bash
# Backend only
cd /opt/sagrn/backend
sudo git pull  # if git is configured
sudo supervisorctl restart sagrn-backend

# Frontend only
cd /opt/sagrn/frontend
sudo npm run build
sudo systemctl reload nginx

# Both
cd /opt/sagrn
sudo git pull
cd backend && sudo supervisorctl restart sagrn-backend
cd ../frontend && sudo npm run build && sudo systemctl reload nginx
```

## Resource Limits

**1GB RAM Raspberry Pi 2**:
- OS: ~150 MB
- Backend (idle): ~100 MB
- Backend (active): ~200-300 MB
- Nginx: ~20 MB
- Database: varies (keep <500 MB)
- Available buffer: 50-200 MB

**Monitor with**: `free -h` and `vmstat 1 5`

## Performance Tips

1. **Close unused processes**: `top` to see what's running
2. **Monitor temperature**: `vcgencmd measure_temp` (should be <60°C)
3. **Optimize database**: Run `sqlite3 /opt/sagrn/data/sagrn.db "VACUUM;"` monthly
4. **Reduce polling**: Increase API feed intervals in code if needed
5. **Use swap wisely**: Swapping is slow on Pi; monitor with `free -h`

## SSH Access

For remote management:

```bash
# Generate SSH key on your machine (if not done)
ssh-keygen -t ed25519 -C "your-email@example.com"

# Copy to Pi
ssh-copy-id -i ~/.ssh/id_ed25519.pub pi@<pi-ip>

# Login without password
ssh pi@<pi-ip>

# Run commands remotely
ssh pi@<pi-ip> 'sudo supervisorctl status'
```

## Logs and Diagnostics

### Application Logs
```bash
# Backend application
sudo tail -f /opt/sagrn/logs/backend.log

# Backend errors only
sudo tail -f /opt/sagrn/logs/backend_error.log

# Nginx access
sudo tail -f /var/log/nginx/access.log

# Nginx errors
sudo tail -f /var/log/nginx/error.log
```

### System Diagnostics
```bash
# Memory usage
free -h

# Disk usage
df -h

# CPU temperature
vcgencmd measure_temp

# Processes
ps aux | grep uvicorn

# Network connections
netstat -tulpn | grep 8000
netstat -tulpn | grep 80
```

## Support Resources

- **Full Installation Guide**: See `RASPBERRYPI_INSTALL_GUIDE.md`
- **Quick Commands**: See `QUICK_REFERENCE.md`
- **Pre-flight Check**: Run `sudo bash preflight_check.sh`
- **Raspberry Pi Docs**: https://www.raspberrypi.com/documentation/
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **React Docs**: https://react.dev/

## Hardware Specifications

**Tested Configuration**:
- Raspberry Pi 2 Model B
- 1GB RAM (shared with GPU)
- 32GB SD Card (works with 16GB, tight with less)
- 5V 2.5A Power Supply
- Heatsink (recommended)

**Expected Performance**:
- Web interface loads: ~1-2 seconds (with SSE updates)
- API response time: <200ms
- Database size: 50-500 MB depending on retention
- CPU usage: 10-40% (idle), 60-100% (peak)

## Security Considerations

1. **SSH**: Disable password auth, use keys only
2. **Updates**: Run `sudo apt-get upgrade` monthly
3. **Firewall**: Consider `ufw` to restrict port access
4. **HTTPS**: Use reverse proxy with SSL (beyond this guide)
5. **Backups**: Backup database regularly

## Uninstall

To remove SAGRN (keeps data intact):

```bash
sudo supervisorctl stop sagrn-backend
sudo systemctl stop nginx
sudo rm -rf /opt/sagrn
sudo userdel sagrn
```

To remove completely (deletes data):

```bash
sudo supervisorctl stop sagrn-backend
sudo systemctl stop nginx
sudo rm -rf /opt/sagrn
sudo userdel sagrn
# Remove database:
# (already deleted in previous step)
```

## Next Steps

1. ✅ Run `preflight_check.sh` to validate your Pi
2. ✅ Run `install_raspberrypi.sh` for automated installation
3. ✅ Access `http://<pi-ip>` in your browser
4. ✅ Edit `/opt/sagrn/.env` to configure external APIs
5. ✅ Monitor logs and system resources
6. ✅ Consider setting up remote access (VPN recommended)

## Support

If you encounter issues:

1. Check **QUICK_REFERENCE.md** for common problems
2. Review detailed **RASPBERRYPI_INSTALL_GUIDE.md**
3. Check application logs with: `sudo tail -f /opt/sagrn/logs/backend.log`
4. Run `htop` to identify resource bottlenecks
5. Verify external connectivity with: `curl https://www.cfs.sa.gov.au/public/feeds/live_incident_feed_text.xml`

---

**Version**: SAGRN Lightweight v2.0+
**Last Updated**: 2026-01-31
**Compatible**: Raspberry Pi 2 Model B, 1GB RAM
**Tested**: Raspberry Pi OS Lite (Bullseye, Bookworm)
