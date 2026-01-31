# SAGRN Lightweight - Raspberry Pi Quick Reference

Quick commands and troubleshooting for SAGRN on Raspberry Pi 2.

## Installation & Setup

```bash
# Pre-flight check (run before installation)
sudo bash scripts/preflight_check.sh

# Run installation script
sudo bash scripts/install_raspberrypi.sh

# After installation, reboot
sudo reboot
```

## Accessing Your Instance

| Method | URL |
|--------|-----|
| Local network | `http://<pi-ip>` |
| Local network (mDNS) | `http://pi.local` |
| Over SSH | `ssh pi@<pi-ip>` |

**Default credentials**: Raspberry Pi OS default user/pass

## Service Management

```bash
# Check all services
sudo supervisorctl status
sudo systemctl status nginx

# Restart backend
sudo supervisorctl restart sagrn-backend

# Restart Nginx
sudo systemctl restart nginx

# Full restart
sudo reboot

# Check if services auto-start on boot
sudo systemctl is-enabled nginx
sudo systemctl is-enabled supervisor
```

## Viewing Logs

```bash
# Backend application log
sudo tail -f /opt/sagrn/logs/backend.log

# Backend errors
sudo tail -f /opt/sagrn/logs/backend_error.log

# Nginx errors
sudo tail -f /var/log/nginx/error.log

# Nginx access
tail -f /var/log/nginx/access.log

# System journal
sudo journalctl -u sagrn -f

# Last 50 lines + follow
sudo tail -50 /opt/sagrn/logs/backend.log -f
```

## System Monitoring

```bash
# Real-time dashboard
htop

# Memory usage
free -h

# Disk usage
df -h
du -sh /opt/sagrn

# CPU temperature
vcgencmd measure_temp

# Network statistics
ifstat

# Process watching
watch -n 1 'ps aux | grep uvicorn'

# Swap usage
vmstat 1 5

# Network connections
netstat -tulpn
```

## Configuration

```bash
# Edit environment variables
sudo nano /opt/sagrn/.env

# Edit Nginx config
sudo nano /etc/nginx/sites-available/sagrn
sudo nginx -t              # Test syntax
sudo systemctl reload nginx # Apply changes

# Edit supervisor config
sudo nano /etc/supervisor/conf.d/sagrn-backend.conf
sudo supervisorctl reread  # Reload config
sudo supervisorctl update  # Apply changes

# Check application config
sudo cat /opt/sagrn/backend/.env
```

## Troubleshooting Checklist

### Issue: Slow/Unresponsive
```bash
# 1. Check memory
free -h

# 2. Check disk
df -h

# 3. Check if backend is running
sudo supervisorctl status sagrn-backend

# 4. Check logs for errors
sudo tail -20 /opt/sagrn/logs/backend_error.log

# 5. Restart backend
sudo supervisorctl restart sagrn-backend

# 6. Reduce data retention (edit .env)
MESSAGE_RETENTION_HOURS=12
sudo supervisorctl restart sagrn-backend
```

### Issue: Backend Won't Start
```bash
# 1. Check status
sudo supervisorctl status sagrn-backend

# 2. View detailed error
sudo tail -50 /opt/sagrn/logs/backend_error.log

# 3. Check port 8000
sudo lsof -i :8000

# 4. Try starting manually
cd /opt/sagrn/backend
source /opt/sagrn/venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5. Check database
sqlite3 /opt/sagrn/data/sagrn.db ".tables"

# 6. Restart supervisor
sudo systemctl restart supervisor
```

### Issue: Web Interface Won't Load
```bash
# 1. Check Nginx status
sudo systemctl status nginx
sudo nginx -t

# 2. Check logs
sudo tail -50 /var/log/nginx/error.log

# 3. Check if frontend built
ls -la /opt/sagrn/frontend/build/

# 4. Rebuild frontend
cd /opt/sagrn/frontend
npm run build
sudo systemctl reload nginx

# 5. Check port 80
sudo lsof -i :80
```

### Issue: External APIs Not Updating
```bash
# 1. Check logs
sudo tail -100 /opt/sagrn/logs/backend.log | grep -i "cfs\|waze\|api"

# 2. Test external connectivity
curl -I https://www.cfs.sa.gov.au/public/feeds/live_incident_feed_text.xml

# 3. Check configured URL
sudo grep "CFS_INCIDENTS" /opt/sagrn/.env

# 4. Test from backend
cd /opt/sagrn/backend
source /opt/sagrn/venv/bin/activate
python -c "
import httpx
url = 'https://www.cfs.sa.gov.au/public/feeds/live_incident_feed_text.xml'
resp = httpx.get(url, timeout=10)
print(resp.status_code)
"
```

### Issue: High CPU Temperature
```bash
# 1. Check temperature
vcgencmd measure_temp

# 2. View process CPU usage
top -b -n 1 | head -15

# 3. Check if throttling
vcgencmd get_throttled

# Solutions:
# - Add heatsink
# - Improve airflow
# - Reduce polling frequency in .env
# - Run during cooler times
```

### Issue: Disk Full
```bash
# 1. Check usage
df -h
du -sh /opt/sagrn/*

# 2. Check database size
ls -lh /opt/sagrn/data/sagrn.db

# 3. Clear logs
sudo truncate -s 0 /opt/sagrn/logs/*.log

# 4. Reduce data retention
# Edit .env: MESSAGE_RETENTION_HOURS=12
sudo supervisorctl restart sagrn-backend

# 5. Clean old data (careful!)
sqlite3 /opt/sagrn/data/sagrn.db "DELETE FROM messages WHERE created_at < datetime('now', '-1 days');"
```

## Useful Commands

```bash
# Copy application files from dev machine
scp -r /path/to/SAGRN pi@192.168.1.100:/tmp/

# Backup database
sudo cp /opt/sagrn/data/sagrn.db /opt/sagrn/data/sagrn.db.backup

# Restore database
sudo cp /opt/sagrn/data/sagrn.db.backup /opt/sagrn/data/sagrn.db

# Check file permissions
ls -la /opt/sagrn/

# Change permissions
sudo chown -R sagrn:sagrn /opt/sagrn

# View Nginx configuration
sudo cat /etc/nginx/sites-available/sagrn

# Test Nginx config
sudo nginx -t -c /etc/nginx/nginx.conf

# Find large files
du -sh /opt/sagrn/* | sort -h

# Monitor bandwidth
nethogs

# Check open ports
sudo netstat -tulpn
```

## Performance Tuning

```bash
# Reduce unnecessary services
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon

# Check and optimize database
sqlite3 /opt/sagrn/data/sagrn.db "PRAGMA optimize;"
sqlite3 /opt/sagrn/data/sagrn.db "VACUUM;"

# View database stats
sqlite3 /opt/sagrn/data/sagrn.db ".schema"

# Monitor system limits
ulimit -a

# Increase file descriptors if needed
# Edit /etc/security/limits.conf
# sagrn soft nofile 65535
# sagrn hard nofile 65535
```

## Emergency Recovery

```bash
# Stop all services (safe mode)
sudo supervisorctl stop sagrn-backend
sudo systemctl stop nginx

# Restore from backup
sudo cp /opt/sagrn/data/sagrn.db.backup /opt/sagrn/data/sagrn.db

# Reset to clean state
sudo rm /opt/sagrn/data/sagrn.db
sudo supervisorctl start sagrn-backend

# Purge and reinstall
sudo bash /path/to/install_raspberrypi.sh
```

## SSH Key Setup (Recommended)

```bash
# Generate key on dev machine
ssh-keygen -t ed25519 -C "your-email@example.com"

# Copy to Pi
ssh-copy-id -i ~/.ssh/id_ed25519.pub pi@192.168.1.100

# Test passwordless login
ssh pi@192.168.1.100

# Disable password auth (on Pi)
sudo nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
# Set: PubkeyAuthentication yes

sudo systemctl restart ssh
```

## Useful Links

- **Raspberry Pi Documentation**: https://www.raspberrypi.com/documentation/
- **Python FastAPI**: https://fastapi.tiangolo.com/
- **React Documentation**: https://react.dev/
- **Nginx Documentation**: https://nginx.org/en/docs/
- **SQLite Documentation**: https://www.sqlite.org/docs.html

## Common Settings

```bash
# Low memory mode
MESSAGE_RETENTION_HOURS=12  # Keep less history
WORKERS=1                    # Use single process
LOG_LEVEL=warn              # Reduce logging verbosity

# Normal mode (1GB+ RAM)
MESSAGE_RETENTION_HOURS=24  # Keep 24h history
WORKERS=2                    # Use 2 processes
LOG_LEVEL=info              # Standard logging

# High memory mode (2GB+ RAM)
MESSAGE_RETENTION_HOURS=72  # Keep 3 days history
WORKERS=4                    # Use 4 processes
LOG_LEVEL=debug             # Verbose logging
```

## Memory Guidelines

| Task | Estimated Usage |
|------|-----------------|
| Base OS | ~100-150 MB |
| Python venv | ~50 MB |
| Backend (idle) | ~100-150 MB |
| Backend (active) | ~200-300 MB |
| Nginx | ~20-30 MB |
| Database | Varies (keep <500 MB) |
| **Total safe** | **~600-800 MB** |

**Available for other tasks**: ~200-400 MB (tight on 1GB)

---

**Last Updated**: 2026-01-31
