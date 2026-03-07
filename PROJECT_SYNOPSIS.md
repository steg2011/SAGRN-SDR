# SAGRN SDR Monitor - Project Synopsis

**Quick Index & Reference for How the App Works**

---

## What Is This?

Real-time emergency services monitoring system for South Australia. Collects pager dispatch messages via RTL-SDR hardware, parses them, and displays on a web dashboard with location enrichment.

**Current Version**: v2 (SQLite + FastAPI, optimized for GCP e2-micro)

---

## The 30-Second Walkthrough

```
Pager Message (FLEX)
    ↓
FastAPI Backend (parse → group → geocode)
    ↓
React Dashboard (real-time SSE updates)
    ↓
User sees incident on map with units & details
```

---

## What Gets Stored?

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| **incidents** | Grouped events by job number | address, latitude, longitude, status, units |
| **messages** | Raw pager messages | raw_message, agency, callsign, timestamp |
| **agencies** | Service definitions | code (SAAS, CFS, MFS, etc), color |
| **incident_units** | Units responding | callsign, status, dispatched_at |
| **locations** | Geocoding cache | address_hash, latitude, longitude |

**Retention**: 24 hours (auto-cleanup every 1 hour)

---

## API Quick Reference

**Data Collection**
- `POST /api/collector/message` — Receive single pager message from Pi
- `POST /api/collector/batch` — Batch messages for sync

**Data Access**
- `GET /api/incidents?limit=20&offset=0` — Paginated incident list
- `GET /api/incidents/{id}` — Full incident detail with messages
- `GET /api/agencies` — List all agencies

**Real-Time**
- `GET /api/events` — Server-Sent Events stream (subscribe for live updates)

**Info**
- `GET /api/stats` — Dashboard stats (count by agency, etc)
- `GET /api/health` — Health check

---

## File Locations

**Backend Services**
- **Parsing**: `backend/app/services/parser.py`
- **Grouping**: `backend/app/services/incident_service.py`
- **Geocoding**: `backend/app/services/geocoder.py`
- **External Data**: `backend/app/services/cfs_integration.py`, `waze_service.py`
- **Real-Time**: `backend/app/services/event_manager.py`

**Frontend Components**
- **Main App**: `frontend/src/App.tsx`
- **Incident Display**: `frontend/src/components/IncidentCard.tsx`
- **Detail Modal**: `frontend/src/components/IncidentDetail.tsx`
- **Filtering**: `frontend/src/components/AgencyFilter.tsx`

**Config & Types**
- **Backend Settings**: `backend/app/core/config.py` (reads `.env`)
- **Database Models**: `backend/app/models/models.py`
- **Frontend Types**: `frontend/src/types/index.ts`

---

## How to Add Common Things

| What | Where | Example |
|------|-------|---------|
| New agency | `incident_service.py` AGENCY_CONFIG dict | `"ABC": AgencyInfo(name="My Service", color="#FF0000")` |
| Message parsing rule | `parser.py` parse() method | Extract new field from FLEX string |
| API endpoint | `api/routes.py` | `@router.get("/api/myendpoint")` |
| React component | `components/` folder | New .tsx file with React.FC<Props> |
| Database field | `models.py` incident/message class | Add Column() to ORM model |
| CSS styling | `App.css` | Single stylesheet for entire app |

---

## Dependencies Quick Check

**Backend**
- FastAPI 0.109.0 | SQLAlchemy 2.0.25 | SQLite + aiosqlite
- APScheduler | RapidFuzz | httpx | Pydantic

**Frontend**
- React 18.2.0 | TypeScript 4.9.5 | Create React App

---

## Running It

**Local Development**
```bash
# Backend
cd backend && python -m venv venv
source venv/bin/activate && pip install -r requirements.txt
python run.py  # http://localhost:8000

# Frontend (separate terminal)
cd frontend && npm install && npm start  # http://localhost:3000
```

**Production (GCP/Pi)**
```bash
./scripts/install_gcp_debian.sh     # Full setup
./scripts/update_gcp.sh             # Update existing
```

---

## Background Tasks (Automatic)

| Task | When | What |
|------|------|------|
| Message Cleanup | Every 60s | Delete messages >24h old |
| CFS Feed Update | Every 5 min | Sync incident status from CFS |
| Waze Feed Update | Every 2 min | Fetch traffic incidents |
| Geocoding Queue | Continuous | Background lookup of addresses |

---

## Environment Variables (Key Ones)

```env
DATABASE_URL=sqlite+aiosqlite:///./data/sagrn.db
CFS_INCIDENTS_XML=https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_current_incidents.xml
MESSAGE_RETENTION_HOURS=24
HOST=0.0.0.0
PORT=8000
WORKERS=1
```

---

## Key Design Decisions

1. **SQLite** not PostgreSQL — Lightweight, no external DB needed, fine for single e2-micro VM
2. **Async everywhere** — FLEX protocol parsing and geocoding need concurrency
3. **Single CSS file** (`App.css`) — No CSS-in-JS or SASS, simpler to maintain
4. **No state library** — React hooks sufficient for this scope
5. **SSE with polling fallback** — Real-time updates, graceful degradation

---

## For More Details

- **Development Guide**: Read `CLAUDE.md` (structures, patterns, all common tasks)
- **Troubleshooting**: See `scripts/QUICK_REFERENCE.md`
- **Database Schema**: See `CLAUDE.md` → Database Schema section

---

**Last Updated**: February 2026
**See Also**: `CLAUDE.md` (developer guide), `README.md` (user docs)
