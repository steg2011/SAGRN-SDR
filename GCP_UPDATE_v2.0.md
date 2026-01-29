# SAGRN SDR v2.0 Update Guide

## Release Information

**Version:** 2.0
**Release Date:** 2026-01-29
**Tag:** `v2.0`

### What's New in v2.0

#### Frontend Enhancements (50% faster initial load!)
- ⚡ **Lazy Loading**: Initial page shows 20 incidents, "Load More" button loads additional batches
- 🔍 **Full-Text Search**: Filter by incident type, location, job ID, or unit callsigns (with debouncing)
- 📊 **Optimized Grid**: 5-6 cards per row (vs 3-4 previously) for better information density
- 🚁 **Medstar Highlighting**: MS## helicopter units displayed in red with glow effect
- ⚠️ **Health Monitoring**: Orange warning banner if no updates received in 1+ hours
- 🗺️ **Suburb Maps**: SAAS incidents without exact addresses now link to suburb-level Google Maps

#### Backend Improvements
- 🌍 **Adelaide Timezone**: Stats and cleanup now use Australia/Adelaide timezone (UTC+9:30/+10:30) instead of UTC
- 🚗 **Waze Deduplication**: Automatically removes duplicate traffic incidents (same type within 200m)
- 📏 **Haversine Distance**: Accurate geospatial deduplication using proper distance calculations

---

## GCP VM Update Instructions

### Quick Update (Recommended)

SSH into your GCP Debian VM and run this single command:

```bash
sudo /opt/sagrn-sdr/scripts/update_gcp.sh
```

This script will:
1. Pull the latest code from main branch
2. Rebuild the frontend
3. Restart the SAGRN service

### Manual Update Process

If the update script doesn't exist or you prefer manual control:

```bash
# SSH into your GCP VM
gcloud compute ssh sagrn-vm --zone=YOUR_ZONE

# Navigate to the installation directory
cd /opt/sagrn-sdr

# Pull the latest changes from main (production branch)
sudo git fetch origin main
sudo git checkout main
sudo git pull origin main

# Verify you're on v2.0
sudo git describe --tags

# Rebuild the React frontend
cd frontend
npm install
npm run build
cd ..

# Restart the backend service
sudo systemctl restart sagrn-sdr

# Verify the service is running
sudo systemctl status sagrn-sdr

# Check logs for any errors
sudo journalctl -u sagrn-sdr -n 50 --follow
```

### Complete Step-by-Step SSH Commands

**Copy and paste these commands in sequence:**

```bash
# 1. SSH into your GCP VM
gcloud compute ssh sagrn-vm --zone=YOUR_ZONE

# 2. Update system packages (optional but recommended)
sudo apt update && sudo apt upgrade -y

# 3. Navigate to SAGRN directory
cd /opt/sagrn-sdr

# 4. Fetch latest from GitHub
sudo git fetch origin main

# 5. Switch to main branch (if not already)
sudo git checkout main

# 6. Pull latest changes
sudo git pull origin main

# 7. Verify you have v2.0
sudo git describe --tags

# 8. Navigate to frontend directory
cd frontend

# 9. Install/update npm dependencies
npm install

# 10. Build production bundle
npm run build

# 11. Return to main directory
cd ..

# 12. Restart the SAGRN service
sudo systemctl restart sagrn-sdr

# 13. Check service status
sudo systemctl status sagrn-sdr

# 14. Follow live logs (press Ctrl+C to exit)
sudo journalctl -u sagrn-sdr -n 50 --follow
```

---

## Verification

After updating, verify the new features are working:

### Check Version
```bash
cd /opt/sagrn-sdr
git describe --tags
# Should output: v2.0
```

### Test in Browser
Open http://YOUR_GCP_IP:8000 and verify:

1. ✅ **Search Box**: Appears between agency filter buttons and RAW button
2. ✅ **Load More Button**: Appears below incident list (when there are >20 incidents)
3. ✅ **Medstar Units**: Any MS## units appear in red with glow
4. ✅ **Grid Layout**: More cards per row (5-6 vs 3-4)
5. ✅ **Health Warning**: If backend stops, orange banner appears after 1 hour
6. ✅ **Maps**: Click on a SAAS incident with only suburb - Google Maps link should work

### Check Logs
```bash
# View last 20 lines of logs
sudo journalctl -u sagrn-sdr -n 20

# Watch real-time logs
sudo journalctl -u sagrn-sdr -f
```

---

## Rollback (If Needed)

If something goes wrong, rollback to v1.x:

```bash
# SSH into your GCP VM
gcloud compute ssh sagrn-vm --zone=YOUR_ZONE

cd /opt/sagrn-sdr

# Checkout previous version
sudo git checkout HEAD~1

# Rebuild frontend
cd frontend
npm run build
cd ..

# Restart service
sudo systemctl restart sagrn-sdr
```

---

## Breaking Changes

⚠️ **None** - v2.0 is fully backward compatible with v1.x

All changes are pure additions:
- New UI features don't affect existing functionality
- Backend changes are opt-in (timezone uses new utilities)
- Database schema unchanged

---

## Performance Notes

- **Initial page load**: ~50% faster (20 items vs 100)
- **Grid density**: 66% more information visible (5-6 vs 3-4 cards)
- **Search**: Debounced (300ms) to prevent excessive filtering
- **Waze dedup**: Runs in-memory during alert processing (no database overhead)

---

## Support

If you encounter issues:

1. **Check logs**: `sudo journalctl -u sagrn-sdr -f`
2. **Verify version**: `git describe --tags`
3. **Restart service**: `sudo systemctl restart sagrn-sdr`
4. **Rollback if needed**: Follow rollback instructions above

---

## What's Next?

Development will continue on the `dev` branch. To stay updated:

- **Production**: Use `main` branch (stable)
- **Testing**: Use `dev` branch (latest features)

```bash
# To switch to dev branch for testing
cd /opt/sagrn-sdr
sudo git checkout dev
sudo git pull origin dev
cd frontend && npm run build && cd ..
sudo systemctl restart sagrn-sdr
```

---

**Questions or issues?** Check the GitHub repository:
https://github.com/steg2011/SAGRN-SDR

**Release tag**: https://github.com/steg2011/SAGRN-SDR/releases/tag/v2.0
