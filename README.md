# SAGRN SDR Monitor (Lightweight Edition)

Emergency services pager monitoring system for South Australia. Monitors the SAGRN (South Australian Government Radio Network) for emergency messages and displays them on a web interface.

**Lightweight Edition** - Optimized for Google Cloud Platform free tier (e2-micro instance).

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Raspberry Pi   │────▶│  GCP VM         │────▶│  Web Browser    │
│  (RTL-SDR +     │     │  (FastAPI +     │     │                 │
│   multimon-ng)  │     │   React Static) │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  SQLite DB      │
                        │  + CFS Feed     │
                        └─────────────────┘
```

## GCP Free Tier Deployment (Recommended)

### One-Command Installation

SSH into your GCP Debian VM and run:

```bash
# Download and run the installation script
curl -fsSL https://raw.githubusercontent.com/steg2011/SAGRN-SDR/dev/scripts/install_gcp_debian.sh | sudo bash
```

Or manually:

```bash
# Clone repository
git clone -b dev https://github.com/steg2011/SAGRN-SDR.git /opt/sagrn-sdr

# Run installation script
cd /opt/sagrn-sdr/scripts
chmod +x install_gcp_debian.sh
sudo ./install_gcp_debian.sh
```

### GCP Firewall Configuration

Create a firewall rule to allow web traffic:

```bash
gcloud compute firewall-rules create sagrn-web \
    --allow tcp:8000 \
    --source-ranges 0.0.0.0/0 \
    --description "SAGRN SDR Monitor web interface"
```

### Update to Latest Version

```bash
sudo /opt/sagrn-sdr/scripts/update_gcp.sh
```

## Local Development Setup

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate
# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create data directory
mkdir -p data

# Run the server
python run.py
```

The API will be available at http://localhost:8000

### 2. Frontend Setup (Development)

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

The frontend will be available at http://localhost:3000

### 3. Frontend Build (Production)

```bash
cd frontend
npm run build
```

The built files will be served automatically by the FastAPI backend.

### 4. Raspberry Pi Collector Setup

Copy `scripts/pi_setup.sh` to your Raspberry Pi and run:

```bash
chmod +x pi_setup.sh
./pi_setup.sh
```

Edit the service configuration:
```bash
sudo nano /etc/systemd/system/sagrn-collector.service
```

Update `SAGRN_SERVER_URL` to your GCP VM's external IP address:
```
SAGRN_SERVER_URL=http://YOUR_GCP_IP:8000
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/collector/message` | POST | Receive single pager message |
| `/api/collector/batch` | POST | Receive batch of messages |
| `/api/incidents` | GET | Get recent incidents |
| `/api/incidents/{id}` | GET | Get incident details |
| `/api/agencies` | GET | Get agency list |
| `/api/stats` | GET | Get dashboard statistics |
| `/api/health` | GET | Health check |
| `/api/events` | GET | Server-Sent Events stream |

## Agency Colors

| Agency | Description | Color |
|--------|-------------|-------|
| SAAS | SA Ambulance Service | Light Green |
| CFS | Country Fire Service | Light Yellow |
| MFS | Metropolitan Fire Service | Light Red |
| SES | State Emergency Service | Light Orange |
| MedStar | MedSTAR | Light Purple |
| TMC | Transport Management Centre | Light Blue |

## Configuration

Copy `backend/.env.example` to `backend/.env` and configure:

- `DATABASE_URL` - Database connection string (default: SQLite)
- `MESSAGE_RETENTION_HOURS` - Hours to keep messages (default: 24)
- `HOST` - Server bind address (default: 0.0.0.0)
- `PORT` - Server port (default: 8000)

## Features

- Real-time pager message monitoring via SSE
- Multi-agency support (SAAS, CFS, MFS, SES, MedStar, TMC)
- CFS incident feed integration (provides location data)
- Incident grouping and unit tracking
- Web interface with agency filtering
- Raw message view mode
- 24-hour message retention (lightweight operation)
- Single-server deployment (FastAPI serves React static files)

## Lightweight Changes (vs Original)

- Removed Nominatim geocoding (uses CFS feed for location data)
- Reduced message retention from 30 days to 24 hours
- Single worker process for low memory usage
- Frontend bundled and served by backend
- Optimized for GCP e2-micro (1GB RAM, 0.25 vCPU)
