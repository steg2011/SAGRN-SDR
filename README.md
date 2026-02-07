# SAGRN SDR Monitor

Emergency services pager monitoring system for South Australia. Monitors the SAGRN (South Australian Government Radio Network) for emergency dispatch messages via RTL-SDR hardware and displays them on a real-time web dashboard.

**Version 2.1** - Docker-native deployment with PostgreSQL, Redis, and containerized collectors.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  RTL-SDR Collectors (Pi, Docker, or Edge Devices)              │
│  - Receive FLEX protocol pager transmissions                   │
│  - Standalone collector.py or Docker container                 │
│  - Send messages to backend(s) via HTTPS/HTTP                 │
└────────────────────────────────────────────────────────────────┘
                              ↓
                    POST /api/collector/message
                              ↓
┌────────────────────────────────────────────────────────────────┐
│  Backend Services (Docker Compose or Manual)                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  FastAPI + Uvicorn (Async, Multi-worker)                │  │
│  │  - Message parsing and validation                        │  │
│  │  - Incident grouping & enrichment                        │  │
│  │  - Real-time SSE updates                                 │  │
│  │  - Static frontend serving                               │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  PostgreSQL 16 (Primary Data Store)                      │  │
│  │  - Incidents, messages, agencies, locations              │  │
│  │  - Replaces SQLite for scalability                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Redis 7 (Cache & Session Store)                         │  │
│  │  - Live incident cache                                   │  │
│  │  - Session management                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  External Integrations (Background Tasks)                │  │
│  │  - CFS incident feed (5-min polling)                     │  │
│  │  - Waze traffic data (2-min polling)                     │  │
│  │  - Data retention cleanup (1-hour cleanup)               │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
                              ↓
                    GET /api/events (SSE)
                    GET /api/incidents
                              ↓
┌────────────────────────────────────────────────────────────────┐
│  Frontend (React 18 + TypeScript - Pre-built)                  │
│  - Real-time incident cards with filtering                     │
│  - Full-text search & agency filtering                         │
│  - Detail modals with related messages                         │
│  - Responsive grid layout                                      │
└────────────────────────────────────────────────────────────────┘
                              ↓
                        Web Browser
```

## Quick Start

### Docker Compose (Recommended)

```bash
# Clone repository
git clone https://github.com/steg2011/SAGRN-SDR.git
cd SAGRN-SDR

# Copy example env file and configure
cp backend/.env.example .env
# Edit .env with your settings (PostgreSQL password, Cloudflare token, etc.)

# Start all services (backend, PostgreSQL, Redis, collector, tunnel)
docker-compose up -d

# View logs
docker-compose logs -f backend
docker-compose logs -f collector

# Access dashboard at http://localhost:8000
```

### Local Development

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py

# Frontend (in another terminal)
cd frontend
npm install
npm start
```

## Deployment Options

### Option 1: GCP with Docker Compose (Recommended)

For production on Google Cloud Platform free tier (e2-micro):

```bash
# 1. Create Debian 12 VM on GCP
gcloud compute instances create sagrn-sdr \
    --image-family debian-12 \
    --image-project debian-cloud \
    --machine-type e2-micro

# 2. SSH and clone repo
gcloud compute ssh sagrn-sdr
git clone https://github.com/steg2011/SAGRN-SDR.git
cd SAGRN-SDR

# 3. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 4. Configure and start
cp backend/.env.example .env
# Edit .env with your database password and Cloudflare tunnel token
sudo docker-compose up -d

# 5. View status
sudo docker-compose ps
```

### Option 2: Raspberry Pi with Standalone Collector

For Pi with RTL-SDR hardware sending to remote backend:

```bash
# 1. Install Python and dependencies
sudo apt-get update
sudo apt-get install -y python3 python3-pip rtl-sdr multimon-ng

# 2. Download collector script
curl -o collector.py https://raw.githubusercontent.com/steg2011/SAGRN-SDR/main/scripts/collector.py

# 3. Configure and run
export SAGRN_SERVER_URL=http://your-backend-host:8000
export COLLECTOR_ID=pi_pager1
export PAGER_FREQUENCY=148.8125M
python3 collector.py
```

### Option 3: Docker on Raspberry Pi

```bash
# Install Docker on Pi
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker pi

# Build and run collector container
docker build -f collector.Dockerfile -t sagrn-collector .
docker run -it --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -e SAGRN_SERVER_URL=http://backend-host:8000 \
  sagrn-collector
```

## Architecture Highlights

### Docker Compose Services

- **db**: PostgreSQL 16 with persistent volume
- **redis**: Redis 7 for caching and sessions
- **backend**: FastAPI application (async, multi-worker)
- **collector**: RTL-SDR to backend bridge (containerized)
- **tunnel**: Cloudflare Tunnel for secure remote access

### Backend Features

- ✅ **Async/Await**: Handles I/O efficiently with Uvicorn workers
- ✅ **PostgreSQL**: Scalable ACID-compliant database
- ✅ **Redis Cache**: Reduces database load, faster queries
- ✅ **Real-time SSE**: Live updates without polling
- ✅ **Message Parsing**: Automatic agency detection and field extraction
- ✅ **External Integration**: CFS incidents & Waze traffic feeds
- ✅ **24-Hour Retention**: Configurable data lifecycle

### Frontend Features

- ✅ **Pre-built Artifacts**: Committed to git for 30-second deployments
- ✅ **Real-time Updates**: SSE stream with instant UI updates
- ✅ **Full-text Search**: Query incidents by type, location, units
- ✅ **Agency Filtering**: Toggle buttons for each service
- ✅ **Responsive Design**: Works on desktop, tablet, mobile
- ✅ **Dark Mode**: Respects system preferences

## Configuration

See `backend/.env.example` for all available options:

```env
# Database
DATABASE_URL=postgresql+asyncpg://sagrn:password@localhost:5432/sagrn

# Cache
REDIS_URL=redis://localhost:6379/0

# Data retention
MESSAGE_RETENTION_HOURS=24

# External feeds
CFS_INCIDENTS_XML=https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_current_incidents.xml

# Collector
COLLECTOR_ID=pager1
PAGER_FREQUENCY=148.8125M

# Cloudflare Tunnel (optional)
CLOUDFLARE_TUNNEL_TOKEN=your-token-here
```

## Supported Agencies

| Agency | Color | Type |
|--------|-------|------|
| SAAS | Green | South Australian Ambulance Service |
| CFS | Yellow | Country Fire Service |
| MFS | Red | Metropolitan Fire Service |
| SES | Orange | State Emergency Service |
| MedStar | Purple | MedSTAR |
| TMC | Blue | Transport Management Centre |
| WAZE | Cyan | Waze Traffic |

## Development

### Building Frontend

```bash
cd frontend
npm install
npm run build
git add build/
git commit -m "Update frontend"
```

### Adding New Agencies

1. Update `backend/app/data/` configuration
2. Create parsing pattern in `backend/app/services/parser.py`
3. Test with mock messages
4. Deploy

### Managing Dependencies

```bash
# Backend
pip install --upgrade -r backend/requirements.txt

# Frontend
npm update --prefix frontend
npm run build --prefix frontend
```

## Troubleshooting

**Backend won't start**
```bash
docker-compose logs backend
# Check DATABASE_URL and REDIS_URL configuration
```

**Collector not sending messages**
```bash
# Test collector connectivity
curl -X POST http://backend:8000/api/health

# Check RTL-SDR device
rtl_test
```

**Database performance issues**
```bash
# Check Redis cache hit rate
docker-compose exec redis redis-cli info stats

# Monitor PostgreSQL
docker-compose exec db psql -U sagrn -d sagrn -c "\dt"
```

## Resources

- **Documentation**: [PROJECT_SYNOPSIS.md](PROJECT_SYNOPSIS.md)
- **Troubleshooting**: [scripts/QUICK_REFERENCE.md](scripts/QUICK_REFERENCE.md)
- **Release Notes**: [RELEASE_SUMMARY.md](RELEASE_SUMMARY.md)
- **Repository**: https://github.com/steg2011/SAGRN-SDR
- **Issues**: https://github.com/steg2011/SAGRN-SDR/issues

## Support

- Check [scripts/QUICK_REFERENCE.md](scripts/QUICK_REFERENCE.md) for common issues
- Review `docker-compose logs` for error messages
- See [PROJECT_SYNOPSIS.md](PROJECT_SYNOPSIS.md) for detailed architecture

---

**Version**: 2.1 | **Last Updated**: February 2026

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

### Core Features
- Real-time pager message monitoring via Server-Sent Events (SSE)
- Multi-agency support (SAAS, CFS, MFS, SES, MedStar, TMC, WAZE)
- CFS incident feed integration (provides location data)
- Waze traffic incident integration with automatic deduplication
- Incident grouping and unit tracking
- Web interface with agency filtering
- Raw message view mode for debugging
- 24-hour message retention (lightweight operation)
- Single-server deployment (FastAPI serves React static files)

### Recent Enhancements (v2.0)
- **Smart Time Handling**: Statistics and cleanup now use Adelaide timezone (UTC+9:30/+10:30) instead of UTC
- **Efficient Lazy Loading**: Initial page load shows 20 incidents, "Load More" button loads additional batches for responsive UI
- **Optimized Grid Layout**: Cards reduced from 3-4 per row to 5-6 cards for better space efficiency
- **Full-Text Search**: Search incidents by type, location, job ID, or assigned unit callsigns with debouncing
- **Poller Health Monitoring**: Displays warning banner if no updates received within 1 hour
- **Suburb-Only Location Links**: SAAS incidents without exact address now link to suburb-level Google Maps
- **Waze Deduplication**: Automatically removes duplicate Waze incidents (same type within 200m using Haversine distance)
- **Medstar Unit Highlighting**: MS## (helicopter) units displayed with red styling and glow effect for visibility

## Lightweight Changes (vs Original)

- Removed Nominatim geocoding (uses CFS feed for location data)
- Reduced message retention from 30 days to 24 hours
- Single worker process for low memory usage
- Frontend bundled and served by backend
- Optimized for GCP e2-micro (1GB RAM, 0.25 vCPU)
