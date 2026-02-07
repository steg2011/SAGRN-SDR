# SAGRN-SDR Project Synopsis

**Last Updated**: February 2026
**Version**: 2.1
**Repository**: https://github.com/steg2011/SAGRN-SDR.git

---

## Executive Summary

SAGRN-SDR is a **real-time emergency services monitoring system** for South Australia. It collects SAGRN (South Australian Government Radio Network) dispatch messages via RTL-SDR hardware and displays incidents on a web dashboard with location enrichment from multiple sources.

**Version 2.1 adds Docker support**, including containerized PostgreSQL, Redis caching, and independent RTL-SDR collectors that can run on Raspberry Pi or other edge devices.

---

## Problem It Solves

Emergency services in South Australia need real-time visibility of dispatch messages. SAGRN-SDR solves this by:
1. Collecting raw pager messages from RTL-SDR hardware (Raspberry Pi or Docker container)
2. Parsing and categorizing by agency automatically
3. Enriching with location data from CFS and Waze feeds
4. Displaying in a real-time responsive dashboard
5. Scaling efficiently with PostgreSQL and Redis caching

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│  RTL-SDR Collectors (Docker or Pi with multimon-ng)          │
│  - Standalone Python script or Docker container              │
│  - POST messages to backend                                  │
│  - Multiple collectors supported                             │
└──────────────────────────────────────────────────────────────┘
                           ↓
               POST /api/collector/message
                           ↓
┌──────────────────────────────────────────────────────────────┐
│  Backend Services (Docker Compose)                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ FastAPI (Uvicorn, Multi-worker async)                 │  │
│  │ - Message validation & parsing                         │  │
│  │ - Incident grouping & enrichment                       │  │
│  │ - Server-Sent Events (SSE) for real-time updates      │  │
│  │ - Static React frontend serving                        │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ PostgreSQL 16 (ACID, Scalable)                         │  │
│  │ - Incidents, messages, agencies, locations             │  │
│  │ - Replaces SQLite for multi-worker concurrency        │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Redis 7 (Cache & Session)                              │  │
│  │ - Live incident cache                                  │  │
│  │ - Session management                                   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                           ↓
                GET /api/events (SSE Stream)
                GET /api/incidents
                           ↓
┌──────────────────────────────────────────────────────────────┐
│  Frontend (React 18 + TypeScript - Pre-built)               │
│  - Real-time incident cards with agency filtering           │
│  - Full-text search                                         │
│  - Detail modals with related messages                      │
│  - Responsive mobile/desktop layout                         │
└──────────────────────────────────────────────────────────────┘
                           ↓
                    Web Browser
```

### Key Design Decisions (v2.1)

1. **PostgreSQL over SQLite**: Multi-worker concurrency, ACID guarantees, horizontal scaling
2. **Redis Cache**: Reduces database load, faster incident queries, session storage
3. **Docker-native**: Compose file handles all infrastructure (db, cache, app, collector, tunnel)
4. **Standalone Collector**: Python script can run anywhere (Pi, Docker, cloud edge)
5. **Pre-built Frontend**: Committed artifacts enable 30-second deployments
6. **Cloudflare Tunnel**: Optional secure remote access without static IP

---

## Technology Stack

### Backend
- **Framework**: FastAPI 0.109.0 (async Python web framework)
- **Server**: Uvicorn 0.27.0 (ASGI with multi-worker support)
- **Database**: PostgreSQL 16 (ACID, scalable, async drivers)
- **Driver**: asyncpg 0.29.0 (async PostgreSQL)
- **Cache**: Redis 7.x (async, hiredis parser)
- **ORM**: SQLAlchemy 2.0 (async session support)
- **Scheduling**: APScheduler 3.10.4 (background tasks)
- **Validation**: Pydantic v2, pydantic-settings
- **HTTP Client**: httpx 0.26.0 (async, connection pooling)
- **Utilities**:
  - RapidFuzz 3.6.1 (fuzzy suburb matching)
  - python-dateutil 2.8.2 (timezone handling)

### Frontend
- **Framework**: React 18.2.0
- **Language**: TypeScript
- **Build Tool**: Create React App with react-scripts 5.0.1
- **Build Output**: Pre-built in `frontend/build/` (static HTML, CSS, JS)

### DevOps & Container
- **Container Orchestration**: Docker Compose (PostgreSQL, Redis, Backend, Collector, Tunnel)
- **Base Images**:
  - Python 3.11-slim (backend, collector)
  - PostgreSQL 16-alpine
  - Redis 7-alpine
  - Cloudflare cloudflared (tunnel)
- **Process**: Uvicorn ASGI workers (1-4 configurable)

---

## File Structure

```
SAGRN-SDR/
├── README.md                          # Main documentation
├── PROJECT_SYNOPSIS.md                # This file
├── RELEASE_SUMMARY.md                 # Release notes
│
├── docker-compose.yml                 # Full stack: DB, cache, app, collector, tunnel
├── Dockerfile                         # Backend container (FastAPI)
├── collector.Dockerfile               # RTL-SDR collector container
│
├── backend/                           # Python FastAPI backend
│   ├── run.py                         # Local development entry point
│   ├── requirements.txt               # Python dependencies
│   ├── .env.example                   # Configuration template
│   ├── app/
│   │   ├── main.py                    # FastAPI app, lifespan, middleware
│   │   ├── api/routes.py              # All API endpoints
│   │   ├── models/
│   │   │   ├── models.py              # SQLAlchemy ORM models
│   │   │   └── database.py            # PostgreSQL session setup
│   │   ├── services/
│   │   │   ├── parser.py              # Message parsing (FLEX protocol)
│   │   │   ├── incident_service.py    # Incident grouping logic
│   │   │   ├── cfs_integration.py     # CFS incident feed (5-min polling)
│   │   │   ├── waze_service.py        # Waze traffic data (2-min polling)
│   │   │   ├── message_combiner.py    # Deduplication
│   │   │   ├── geocoder.py            # Address → coordinates
│   │   │   ├── suburb_matcher.py      # Fuzzy suburb matching
│   │   │   └── event_manager.py       # SSE stream management
│   │   ├── core/
│   │   │   └── config.py              # Pydantic settings from env
│   │   ├── utils/
│   │   │   └── timezone.py            # Adelaide TZ (UTC+9:30/+10:30)
│   │   └── data/
│   │       └── sa_suburbs.py          # South Australian suburbs list
│   └── data/
│       └── (PostgreSQL only, no local DB)
│
├── frontend/                          # React TypeScript frontend
│   ├── package.json                   # NPM dependencies
│   ├── src/
│   │   ├── App.tsx                    # Main component
│   │   ├── App.css                    # Responsive styles
│   │   ├── index.tsx                  # React entry point
│   │   ├── types/index.ts             # TypeScript interfaces
│   │   ├── services/api.ts            # API client & SSE
│   │   └── components/
│   │       ├── IncidentCard.tsx       # Incident display
│   │       ├── IncidentDetail.tsx     # Modal detail view
│   │       ├── AgencyFilter.tsx       # Filter buttons
│   │       ├── SearchBar.tsx          # Full-text search
│   │       └── RawMessageCard.tsx     # Debug view
│   ├── public/index.html              # HTML shell
│   └── build/                         # Pre-built production artifacts
│       ├── index.html
│       └── static/
│
├── scripts/                           # Deployment & utility scripts
│   ├── collector.py                   # Standalone RTL-SDR collector
│   ├── host_prepare.sh                # System prep for Pi/GCP
│   ├── install_gcp_debian.sh          # GCP installation (legacy)
│   ├── install_raspberrypi.sh         # Pi installation (legacy)
│   ├── pi_setup.sh                    # RTL-SDR hardware setup
│   ├── preflight_check.sh             # System requirements
│   ├── QUICK_REFERENCE.md             # Troubleshooting guide
│   ├── check_db.py                    # Database diagnostics
│   └── migrate_agency.py              # Data migration utilities
│
└── .github/                           # GitHub Actions CI/CD
    └── workflows/                     # Automated testing & deployment
```

---

## Database Schema (PostgreSQL)

### Tables (SQLAlchemy Async Models)

#### `agencies`
Emergency service agencies with visual identity
- `id` (PK), `code` (UNIQUE), `name`, `color`, `created_at`, `updated_at`

#### `messages`
Raw pager messages from collectors
- `id` (PK), `agency_id` (FK), `address_code`, `message_type`, `message_text`, `raw_message`
- `incident_num`, `job_type`, `priority`, `location`, `units`, `timestamp`, `received_at`

#### `incidents`
Grouped incidents (multiple messages per incident)
- `id` (PK), `agency_id` (FK), `unique_id` (UNIQUE: "{AGENCY}_{INCIDENTNUM}_{YYYYMMDD}")
- `incident_num`, `incident_type`, `location`, `units`, `priority`
- `latitude`, `longitude`, `message_count`, `latest_message`
- `created_at`, `updated_at`

#### `incident_units`
Units assigned to incidents
- `id` (PK), `incident_id` (FK), `unit_name`, `status`

#### `cap_codes`
Pager address code lookup
- `address_code` (PK), `agency_id` (FK), `location`

#### `job_types` & `crew_abbreviations`
Lookup tables for SAAS job/crew expansion

#### `locations`
Geocoding cache
- `id` (PK), `address` (UNIQUE), `latitude`, `longitude`, `cached_at`

#### `sa_streets`
South Australian street names for fuzzy matching
- `street_name` (PK)

---

## Configuration

### Environment Variables (`backend/.env`)

```env
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://sagrn:password@db:5432/sagrn

# Redis Cache
REDIS_URL=redis://redis:6379/0

# Server
HOST=0.0.0.0
PORT=8000
WORKERS=2  # Configurable, 1-4 typical

# Data Retention
MESSAGE_RETENTION_HOURS=24

# External Feeds
CFS_INCIDENTS_XML=https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_current_incidents.xml
CFS_CAP_XML=https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_cap_incidents.xml
WAZE_ENABLED=true
GEOCODING_ENABLED=true

# Static Frontend
STATIC_DIR=/app/frontend_build

# Cloudflare Tunnel (optional)
CLOUDFLARE_TUNNEL_TOKEN=your-token-here
```

---

## Deployment Options

### Option 1: Docker Compose (Recommended for Production)

**All-in-one stack** with PostgreSQL, Redis, Backend, Collector, and Cloudflare Tunnel:

```bash
git clone https://github.com/steg2011/SAGRN-SDR.git
cd SAGRN-SDR
cp backend/.env.example .env
# Edit .env with your database password and settings
docker-compose up -d
```

**Services:**
- **db** (PostgreSQL 16): Port 5432 (internal only by default)
- **redis** (Redis 7): Port 6379 (internal only)
- **backend** (FastAPI): Port 8000 (expose to web)
- **collector** (RTL-SDR): Sends to backend (privileged container)
- **tunnel** (Cloudflare): Optional secure remote access

**Specifications:**
- CPU: Single worker optimized, scales to 4 workers with more RAM
- Memory: 512MB minimum (PostgreSQL + backend + Redis)
- Storage: 10GB recommended for message retention
- Cost: Free tier on GCP e2-micro eligible

### Option 2: Local Development

```bash
# Backend (PostgreSQL/Redis must be running separately)
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Ensure DATABASE_URL and REDIS_URL point to local instances
python run.py

# Frontend (development server with hot reload)
cd frontend
npm install
npm start
```

### Option 3: Raspberry Pi with Standalone Collector

```bash
# 1. Install dependencies
sudo apt-get update
sudo apt-get install -y python3 python3-pip rtl-sdr multimon-ng

# 2. Run standalone collector
export SAGRN_SERVER_URL=http://your-backend:8000
export COLLECTOR_ID=pi_pager1
export PAGER_FREQUENCY=148.8125M
python3 scripts/collector.py
```

---

## API Endpoints

### Collector Endpoints (Data Ingest)
```
POST /api/collector/message
  Body: {"message": "...", "collector_id": "pi1", "timestamp": "2026-02-07T..."}
  Response: {status: "success", incident_id: "SAAS_12345_20260207"}

POST /api/collector/batch
  Body: [{...}, {...}]
  Response: {processed: 3, created: 2, updated: 1}
```

### Incident Endpoints (Frontend Data)
```
GET /api/incidents?limit=20&offset=0
  Response: {
    incidents: [{id, agency, type, location, units, timestamp}],
    total: 1523,
    hasMore: true
  }

GET /api/incidents/{id}
  Response: {incident, messages, related_waze}

GET /api/agencies
  Response: [{code, name, color}, ...]

GET /api/stats
  Response: {total_incidents, total_messages, by_agency, timestamp}
```

### Real-time
```
GET /api/events
  Response: Server-Sent Events stream
  Events: "new_incident", "incident_updated"
```

---

## Performance Characteristics

### Throughput
- **Peak Capacity**: 200-500 messages/hour (depends on worker count and query complexity)
- **Typical Load**: 50-150 messages/hour
- **Backend Latency**: <50ms per message (PostgreSQL + Redis)

### Database
- **Query Performance**: <5ms for incident list (indexed by timestamp, agency)
- **Write Performance**: <10ms per message (async batching)
- **Storage**: ~2MB per 1000 messages
- **Concurrent Connections**: PostgreSQL handles multiple workers efficiently

### Resource Usage
- **CPU**: 10-20% average (I/O bound, multiple workers)
- **Memory**: 150-300MB backend + 100MB Redis + 200MB PostgreSQL
- **Disk I/O**: Low (async queries, connection pooling via Redis)

---

## Supported Agencies

| Agency | Code | Color | Type |
|--------|------|-------|------|
| SAAS | SAAS | Green | SA Ambulance Service |
| CFS | CFS | Yellow | Country Fire Service |
| MFS | MFS | Red | Metropolitan Fire Service |
| SES | SES | Orange | State Emergency Service |
| MedStar | MedStar | Purple | MedSTAR |
| TMC | TMC | Blue | Transport Management Centre |
| Waze | WAZE | Cyan | Waze Traffic |

---

## Development Workflow

### Adding a New Feature

1. **Backend changes**: Modify services, add routes, update models
2. **Database migration**: Update SQLAlchemy models (auto-creates on startup)
3. **Frontend changes**: Update React components, types
4. **Build frontend**: `cd frontend && npm run build`
5. **Test locally**: `docker-compose up` or local dev setup
6. **Commit**: Both backend and frontend/build/ artifacts
7. **Push**: `git push origin main`

### Updating Dependencies

```bash
# Backend
pip list --outdated
pip install --upgrade <package>
pip freeze > backend/requirements.txt

# Frontend
npm outdated
npm update
npm run build
```

---

## Troubleshooting

**Backend won't start**
```bash
docker-compose logs backend
# Check DATABASE_URL syntax, PostgreSQL health
docker-compose ps db
```

**Collector not sending messages**
```bash
docker-compose logs collector
# Verify SAGRN_SERVER_URL points to backend
# Check RTL-SDR device: rtl_test
```

**Database performance issues**
```bash
# Check Redis cache effectiveness
docker-compose exec redis redis-cli info stats

# Monitor PostgreSQL
docker-compose exec db psql -U sagrn -d sagrn -c "SELECT count(*) FROM incidents;"
```

**Frontend not loading**
```bash
# Ensure frontend is built
ls frontend/build/index.html

# Check static file serving
docker-compose logs backend | grep static
```

---

## Version History

- **v2.1** (Feb 2026): Docker Compose support, PostgreSQL + Redis, standalone collector, Cloudflare Tunnel
- **v2.0** (Jan 2026): Lightweight single-worker, smart time handling, full-text search
- **v1.0** (Initial): Basic incident monitoring, multi-agency support

---

## Contact & Support

- **Repository**: https://github.com/steg2011/SAGRN-SDR
- **Issues**: GitHub Issues
- **Documentation**: README.md, PROJECT_SYNOPSIS.md, QUICK_REFERENCE.md

---

**Last Updated**: February 7, 2026
**Maintainer**: steg2011
