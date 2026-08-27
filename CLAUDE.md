# SAGRN SDR Monitor - Development Guide

Ensure claude.md file is updated whenever there is a change to the core code that may change the meaning of claude.md

## jcodemunch MCP Setup

jcodemunch is used for code search/navigation. The project folder name contains a space which the tool cannot handle, so a workaround is required each session.

**Indexed repo name**: `local/sagrn_tmp`

**Steps to enable at the start of each session:**

1. Load the tools (ToolSearch):
   - `select:mcp__jcodemunch__index_folder,mcp__jcodemunch__list_repos`

2. Check if already indexed (optional):
   ```
   mcp__jcodemunch__list_repos
   ```

3. If not indexed, copy project to a spaceless temp path and index it:
   ```powershell
   New-Item -ItemType Directory -Path 'C:\sagrn_tmp' -Force
   Copy-Item -Path 'C:\Users\bradc\Documents\Development\SAGRN Lightweight\*' -Destination 'C:\sagrn_tmp' -Recurse -Force -Exclude @('node_modules','venv','__pycache__','*.db','.git','build','dist')
   ```
   Then call `mcp__jcodemunch__index_folder` with path `C:\sagrn_tmp` and `extra_ignore_patterns: ["node_modules","venv","__pycache__","*.pyc","build","dist",".git","*.db"]`

4. After making code changes, re-index incrementally:
   - Call `mcp__jcodemunch__index_folder` with `path: C:\sagrn_tmp` and `incremental: true`

**Available tools after loading**: `get_repo_outline`, `get_file_outline`, `get_file_tree`, `search_symbols`, `search_text`, `get_symbol`, `get_symbols`


> Real-time emergency services pager monitoring system for South Australia (SAGRN)
> **Primary Setup**: Docker Compose on on-prem Intel NUC (PostgreSQL + Redis + Cloudflare Tunnel)
> **Legacy Setups**: SQLite on GCP e2-micro or Raspberry Pi (still supported via scripts)

## Quick Reference

- **What**: Collect, parse, and display emergency dispatch messages in real-time
- **How**: RTL-SDR → Pager messages → FastAPI parsing → React dashboard
- **Where**: South Australian Government Radio Network (SAGRN/SAGES)
- **Stack**: Python (FastAPI), TypeScript (React), PostgreSQL (Docker) or SQLite (legacy), async/await everywhere

## Project Structure

```
SAGRN Lightweight/
├── Dockerfile                  # Multi-stage: Node.js builds frontend, Python serves all
├── collector.Dockerfile        # RTL-SDR pager collector container
├── docker-compose.yml          # Full orchestration: db, redis, backend, collector, tunnel
│
├── .github/
│   └── workflows/
│       └── ci.yml             # CI gate: ruff, pytest, tsc (no deploy - see below)
│
├── backend/                    # Python FastAPI async backend
│   ├── app/
│   │   ├── api/routes.py       # All API endpoints (incidents, collector, events)
│   │   ├── admin/              # Admin dashboard (separate FastAPI app, own container)
│   │   │   ├── main.py         # Admin app: auth routes + stats/logs/visitors API
│   │   │   ├── auth.py         # HMAC signed-cookie sessions (stdlib only)
│   │   │   ├── system_stats.py # Host CPU/mem/disk/temp from mounted /host/proc, /host/sys
│   │   │   ├── docker_client.py# Docker Engine API over unix socket (httpx UDS)
│   │   │   └── templates/      # dashboard.html + login.html (self-contained, no build step)
│   │   ├── models/
│   │   │   ├── database.py     # SQLAlchemy async session + engine setup
│   │   │   └── models.py       # ORM: Agency, Message, Incident, Location, Unit types
│   │   ├── services/           # Business logic layer
│   │   │   ├── parser.py                # FLEX protocol → ParsedMessage
│   │   │   ├── incident_service.py      # Grouping & deduplication logic
│   │   │   ├── message_combiner.py      # Multi-part message reassembly
│   │   │   ├── geocoder.py              # Nominatim + cache for lat/lon
│   │   │   ├── suburb_matcher.py        # RapidFuzz SA suburb fuzzy matching
│   │   │   ├── event_manager.py         # SSE broadcast management
│   │   │   ├── cfs_integration.py       # CFS XML feed polling (5-min)
│   │   │   └── waze_service.py          # Waze traffic data (2-min)
│   │   ├── core/
│   │   │   └── config.py       # Pydantic settings from environment
│   │   ├── utils/timezone.py   # Adelaide TZ (UTC+9:30/+10:30)
│   │   ├── data/sa_suburbs.py  # South Australian suburb list
│   │   └── main.py             # FastAPI app init + lifespan hooks
│   ├── requirements.txt        # Python dependencies
│   ├── run.py                  # Local dev server entry point
│   └── .env.example            # Environment variable template
│
├── frontend/                   # React 18 + TypeScript
│   ├── src/
│   │   ├── App.tsx             # Main component + hooks-based state
│   │   ├── App.css             # Single unified stylesheet
│   │   ├── index.tsx           # React entry point
│   │   ├── types/index.ts      # Shared TypeScript interfaces
│   │   ├── services/api.ts     # API client + SSE consumer
│   │   ├── data/
│   │   │   ├── ditRoads.ts            # DIT state-maintained road names + isDitRoad()
│   │   │   └── ditMotorways.ts        # DIT motorway/freeway/expressway matcher
│   │   └── components/
│   │       ├── IncidentCard.tsx       # Card incident display (TILES view)
│   │       ├── IncidentRow.tsx        # Single-line incident display (COMPACT view)
│   │       ├── IncidentDetail.tsx     # Modal detail view
│   │       ├── IncidentMap.tsx        # Mapbox GL map (MAP view)
│   │       ├── FilterMenu.tsx         # Slide-out agency filter panel
│   │       ├── AgencyFilter.tsx       # Agency toggle menu (superseded by FilterMenu)
│   │       ├── SearchBar.tsx          # Full-text search (pop-out field in the header)
│   │       └── RawMessageCard.tsx     # Debug message viewer
│   ├── package.json
│   ├── tsconfig.json
│   └── public/index.html
│
├── scripts/                    # Deployment & database utilities
│   ├── auto_deploy.sh          # Pull-based deploy, run from cron every 5 min
│   ├── host_prepare.sh         # Intel NUC Docker host setup (users, udev, drivers)
│   ├── collector.py            # RTL-SDR to HTTP collector script
│   ├── install_gcp_debian.sh   # GCP Debian VM setup script (legacy)
│   ├── update_gcp.sh           # Update existing GCP installation (legacy)
│   ├── install_raspberrypi.sh  # Raspberry Pi full setup (legacy)
│   ├── pi_setup.sh             # Raspberry Pi collector-only setup
│   ├── preflight_check.sh      # System requirements check (RPi)
│   ├── check_db.py             # Database inspection tool
│   ├── import_logs.py          # Import historical data
│   ├── migrate_agency.py       # Schema migrations
│   └── update_agency_colors.py # Agency color updates
│
├── data/
│   └── sagrn.db                # SQLite database (local dev, auto-created)
│
├── CLAUDE.md                   # This file (developer guide)
└── PROJECT_SYNOPSIS.md         # Quick reference index
```

## Tech Stack

### Backend
| Component | Technology | Version |
|-----------|------------|---------|
| Framework | FastAPI | 0.109.0 |
| Server | Uvicorn | 0.27.0 |
| ORM | SQLAlchemy (async) | 2.0.25 |
| Database | SQLite + aiosqlite | 0.19.0 |
| Scheduler | APScheduler | 3.10.4 |
| HTTP Client | httpx | 0.26.0 |
| Validation | Pydantic | 2.5.3 |
| Fuzzy Match | rapidfuzz | 3.6.1 |
| Python | 3.8+ | - |

### Frontend
| Component | Technology | Version |
|-----------|------------|---------|
| Framework | React | 18.2.0 |
| Language | TypeScript | 4.9.5 |
| Build | Create React App | 5.0.1 |
| State | React hooks (no Redux) | - |
| Styling | Plain CSS (App.css) | - |

### Real-Time
- Server-Sent Events (SSE) via `/api/events`
- Fallback polling every 30 seconds

### External Integrations
- **CFS XML Feed**: `https://data.eso.sa.gov.au/prod/cfs/criimson/` (5-min refresh)
- **Waze Traffic API**: 2-min refresh with 200m deduplication
- **SA Power Networks outages**: `https://outage.apps.sapowernetworks.com.au/Outages/GetPublicisedCurrentOutages/`
  (5-min refresh). Each outage is mirrored into an `Incident` (agency `SAPN`) so it
  appears in the job list/filter/detail, plus a companion `PowerOutage` row holding
  the affected-area polygon and outage-specific detail. See `services/sapn_service.py`.

### Client-Side Filters (FilterMenu)

All agency filters are applied client-side, in two places that must stay in sync:
`App.tsx` (`visibleIncidents`) for the list views and `IncidentMap.tsx`
(`filteredIncidents`) for the map. Adding a filter means touching `AgencyFilters` in
`types/index.ts`, both filter blocks, and `FilterMenu.tsx`.

The WAZE section carries three sub-filters:
- **Crashes Only** - `incident_type` contains "accident"; independent of the other two
- **DIT Roads** - `isDitRoad()`, the full state-maintained road list
- **Motorways** - `isDitMotorway()`, the five roads DIT classifies as
  MOTORWAY/FREEWAY/EXPRESSWAY: South Eastern Fwy, North South Mwy, Southern Exp,
  Northern Exp, Port River Exp (plus their ramps)

DIT Roads and Motorways are mutually exclusive - motorways are a subset of DIT roads,
so selecting one clears the other. Both data files derive from the data.sa.gov.au
'State Maintained Roads' dataset, mirrored locally in the `sa_roads` table; the
motorway list is `SELECT DISTINCT road_name FROM sa_roads WHERE road_type IN
('MOTORWAY','FREEWAY','EXPRESSWAY')`.

## Coding Standards

### Python (Backend)

**Indentation**: 4 spaces (PEP 8)

**Naming**:
- `snake_case` - functions, variables, files
- `PascalCase` - classes
- `UPPER_CASE` - constants
- `_prefix` - private methods

**Patterns**:
```python
# Async everywhere
async def process_message(
    self,
    db: AsyncSession,
    parsed: ParsedMessage
) -> Optional[Message]:
    """Docstring for public methods."""
    async with async_session() as db:
        # Database operations
        pass

# Type hints required
class IncidentService:
    AGENCY_CONFIG: Dict[str, AgencyInfo] = {...}

    async def get_incidents(
        self,
        db: AsyncSession,
        limit: int = 20,
        offset: int = 0
    ) -> List[Incident]:
        pass
```

**Database Access**:
```python
# Always use async context manager
async with async_session() as db:
    result = await db.execute(select(Message).where(...))
    messages = result.scalars().all()
```

### TypeScript (Frontend)

**Indentation**: 2 spaces

**Naming**:
- `PascalCase` - components, interfaces, types
- `camelCase` - functions, variables, props
- `UPPER_CASE` - constants

**Patterns**:
```typescript
// Typed functional components
interface IncidentCardProps {
  incident: Incident;
  isNew?: boolean;
  onClick: () => void;
}

export const IncidentCard: React.FC<IncidentCardProps> = ({
  incident,
  isNew,
  onClick
}) => {
  // Hooks at top
  const [expanded, setExpanded] = useState(false);
  const handleClick = useCallback(() => {...}, []);

  return <div>...</div>;
};

// Interfaces for all data structures
interface Incident {
  id: string;
  agency_code: string;
  timestamp: string;
  location?: string;
  units: string[];
}
```

**State Management**:
- `useState` for local state
- `useEffect` for side effects
- `useCallback` for memoized handlers
- `useRef` for tracking across renders
- No Redux/external state libraries

### General Rules

1. **Async/Await**: All I/O operations are async
2. **Type Safety**: Full type hints (Python) / strict mode (TS)
3. **Error Handling**: Try/except blocks with specific exceptions
4. **Single File CSS**: All styles in `frontend/src/App.css`
5. **Adelaide Timezone**: Use `backend/app/utils/timezone.py` helpers

## Command Guide

### Development

```bash
# Backend (from backend/)
python -m venv venv                  # Create virtual env
source venv/bin/activate             # Activate (Linux/Mac)
.\venv\Scripts\activate              # Activate (Windows)
pip install -r requirements.txt      # Install deps
python run.py                        # Start dev server :8000

# Frontend (from frontend/)
npm install                          # Install deps
npm start                            # Start dev server :3000
npm run build                        # Production build
```

### Production Deployment (NUC)

**Deployment is pull-based.** GitHub Actions cannot reach the NUC - its only
public ingress is the Cloudflare Tunnel, which carries HTTP rather than SSH - so
the NUC polls for new commits and deploys itself.

```
push to main -> GitHub Actions (ci.yml: ruff, pytest, tsc)
             -> NUC cron, every 5 min: scripts/auto_deploy.sh
             -> deploys only if lint-and-test passed for that commit
```

`scripts/auto_deploy.sh` (cron as the repo owner, log at `data/auto_deploy.log`):
- deploys only a commit whose `lint-and-test` job concluded success; holds and
  retries if CI is still running or the API is unreachable
- refuses to run over a dirty working tree, and fast-forwards only
- recreates **backend + admin** only. The collector is included just when
  `collector.Dockerfile` or `scripts/collector.py` changed, so a frontend or
  backend release never interrupts pager capture
- rolls back to the previous commit if compose fails or `/api/health` does not
  answer afterwards; `flock` prevents overlapping runs

`.env` lives only on the NUC and is never rewritten by a deploy. `MAPBOX_TOKEN`,
`ADMIN_PASSWORD` and `ADMIN_SECRET_KEY` exist nowhere else - do not add a step
that regenerates `.env` from GitHub secrets, which is what the old SSH deploy job
did and would have taken out the map view and the admin login.

`ruff.toml` pins the lint rule set explicitly and `ci.yml` pins `ruff==0.16.4`,
because ruff's built-in defaults widened between 0.15 and 0.16 and silently
turned the gate red on unchanged code.

Manual deploy, if ever needed:
```bash
docker compose build backend && docker compose up -d backend admin
```

Legacy setups (still supported via scripts):
```bash
# GCP Debian VM
./scripts/install_gcp_debian.sh      # Fresh install
./scripts/update_gcp.sh              # Update existing

# Raspberry Pi Collector
./scripts/install_raspberrypi.sh     # Setup collector
./scripts/pi_setup.sh                # Configure FLEX protocol
```

### Database Utilities

```bash
python scripts/check_db.py           # Inspect database
python scripts/import_logs.py        # Import historical data
python scripts/migrate_agency.py     # Schema migrations
```

### System Validation

```bash
./scripts/preflight_check.sh         # Validate config
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/collector/message` | POST | Receive pager message |
| `/api/collector/batch` | POST | Receive batch messages |
| `/api/incidents` | GET | List incidents (paginated) |
| `/api/incidents/{id}` | GET | Incident details |
| `/api/outages` | GET | Active SAPN power outages w/ affected-area polygons (map) |
| `/api/agencies` | GET | Agency list |
| `/api/stats` | GET | Dashboard stats |
| `/api/health` | GET | Health check |
| `/api/events` | GET | SSE stream |
| `/api/messages/raw` | GET | Raw messages |

## Admin Dashboard (admin.sagrn.tmc-sa.org)

Separate FastAPI app (`backend/app/admin/`) running as the `admin` compose service
on port 8100 (bound to 127.0.0.1; public access only via the Cloudflare tunnel
hostname `admin.sagrn.tmc-sa.org` → `http://admin:8100`). It is deliberately a
separate container so the Docker socket and host mounts are never exposed to the
public backend.

- **Auth**: password login (`ADMIN_PASSWORD` in `.env`), 12h HMAC signed-cookie
  session (`ADMIN_SECRET_KEY`), login rate limiting. No extra dependencies.
- **Shows**: host CPU/mem/disk/load/temp (from `/host/proc`, `/host/sys` mounts),
  Docker container status + per-container CPU/mem (docker.sock, mounted ro),
  SDR receiver details (collector env + message throughput from DB + collector
  log tail from the `collector_logs` volume), log faults (error/warning lines
  scanned from all container logs), and site visitor analytics.
- **Visitor tracking**: middleware in `app/main.py` records page loads (GET,
  non-API/static) to the `visits` table with CF-Connecting-IP / CF-IPCountry.
- **Endpoints**: `/api/login`, `/api/logout`, `/api/overview`, `/api/faults`,
  `/api/logs?container=`, `/api/visitors` (all auth-gated except login/health).
- The admin service reuses the backend image (`image: sagrn-sdr-backend`), so
  `docker compose build backend && docker compose up -d admin backend` deploys both.

## Database Schema (SQLite)

### Core Tables

**agencies**
- `id`, `code` (UNIQUE), `name`, `color` (hex)
- Services: SAAS, CFS, MFS, SES, MedStar, TMC, WAZE, SAPN

**messages**
- `id`, `raw_message`, `timestamp`, `received_at`
- FLEX protocol: `flex_speed`, `flex_frame`, `capcode`
- Parsed: `agency_id` (FK), `incident_id` (FK), `callsign`, `priority`, `location_text`, `job_id`, `incident_type`, `message_type`, `is_duplicate`
- Indexes: `(timestamp, agency_id)`, `(job_id, timestamp)`

**incidents**
- `id`, `unique_id` (UNIQUE), `agency_id` (FK), `incident_number`, `incident_date`
- Details: `incident_type`, `alarm_level`, `status`, `address`, `suburb`, `map_reference`
- **Location**: `latitude`, `longitude` (geocoded), `geocode_attempted`, `geocode_success`
- Tracking: `created_at`, `updated_at`, `closed_at`, `cfs_status`, `cfs_last_update`
- Index: `(incident_date, agency_id)`

**incident_units**
- `id`, `incident_id` (FK), `callsign`, `dispatched_at`, `status`
- Index: `(incident_id, callsign)`

**power_outages** (SA Power Networks, 1:1 with a SAPN `Incident`)
- `id`, `job_id` (UNIQUE), `incident_id` (FK), `active`
- `is_planned`, `reason` (cause), `status_text`, `affected_customers`
- `primary_suburb`, `suburbs` (JSON), `geometry` (JSON `[[lng,lat],...]`), `centroid_lat/lng`
- `start_time`, `estimated_restoration` (naive UTC; feed provides Adelaide-local)
- Accessed via `Incident.power_outage`; exposed on `IncidentResponse.outage`

### Lookup & Cache Tables

**locations** (Geocoding cache)
- `id`, `address_hash` (UNIQUE), `original_address`, `normalized_address`
- `latitude`, `longitude` (from Nominatim), `geocode_success`, `geocode_source`
- `created_at` (when cached)
- One entry per unique address to avoid redundant geocoding API calls

**capcodes**, **job_types**, **crew_abbreviations**
- Lookup tables for FLEX message expansion

**sa_streets**
- `street_name` (indexed), `suburb`, `postcode`, `full_address`
- Used by fuzzy matching in geocoding

## How It Works

### Data Flow
```
┌─────────────────────┐
│  Pager Hardware     │ ← RTL-SDR captures FLEX protocol messages
│  (Raspberry Pi)     │   POST /api/collector/message
└──────────┬──────────┘
           ↓
┌─────────────────────────────────────────┐
│  FastAPI Backend (GCP e2-micro)        │
│  ├─ Parse FLEX → ParsedMessage         │
│  ├─ Group by job_id → Incident         │
│  ├─ Geocode address → lat/lon          │
│  ├─ Fetch CFS/Waze enrichment          │
│  └─ Broadcast via SSE /api/events      │
└──────────┬──────────────────────────────┘
           ↓
┌──────────────────────┐
│  Web Browser         │ ← React UI subscribes to /api/events
│  (React Dashboard)   │   Shows incidents in real-time
└──────────────────────┘
```

### Message Processing Pipeline

1. **Ingest**: Message arrives via POST /api/collector/message
2. **Parse**: `MessageParser` extracts FLEX protocol fields
   - FLEX speed/frame, agency, callsign, priority, location text, units, job type
3. **Combine**: `MessageCombiner` reassembles multi-part messages
4. **Group**: `IncidentService` finds or creates incident by unique_id
   - `unique_id` format: `{AGENCY_CODE}_{INCIDENT_NUM}_{YYYYMMDD}`
5. **Enrich**:
   - Suburb matching: `SuburbMatcher` fixes typos in location text
   - Geocoding: `GeocoderService` looks up address → lat/lon (with caching)
   - External feeds: `CFSIntegration` & `WazeService` add context
6. **Broadcast**: `EventManager` sends SSE event to connected clients
7. **Cleanup**: Automatic hourly cleanup removes messages >24 hours old

### Background Services (Async Scheduled)

| Task | Frequency | Purpose |
|------|-----------|---------|
| Message cleanup | Every 60 sec | Delete messages older than 24h |
| CFS feed update | Every 5 min | Sync incident status from CFS XML |
| Waze feed update | Every 2 min | Fetch traffic incident markers |
| SAPN outage update | Every 5 min | Sync SA Power Networks outages (area polygons) |
| Geocoding process | Continuous | Background lat/lon lookup queue |

### Real-Time Updates

**Server-Sent Events** (`GET /api/events`)
- Client subscribes on page load
- Backend broadcasts on new message: `{type: "new_message", incident_id, agency, timestamp}`
- Automatic reconnect on disconnect
- Fallback polling every 30 seconds if SSE fails

## Environment Variables

```env
DATABASE_URL=sqlite+aiosqlite:///./data/sagrn.db
CFS_INCIDENTS_XML=https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_current_incidents.xml
CFS_CAP_XML=https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_cap_incidents.xml
MESSAGE_RETENTION_HOURS=24
HOST=0.0.0.0
PORT=8000
WORKERS=1
# Admin dashboard
ADMIN_PASSWORD=<login password for admin.sagrn.tmc-sa.org>
ADMIN_SECRET_KEY=<random hex, signs session cookies>
```

## Development Reference

### Common Tasks & Key Files

| Task | Primary File | Details |
|------|--------------|---------|
| Add/modify agency | `backend/app/services/incident_service.py` | Update AGENCY_CONFIG dict (code, name, color) |
| Parse new message format | `backend/app/services/parser.py` | Modify ParsedMessage class and parse() logic |
| Add API endpoint | `backend/app/api/routes.py` | Add @router function, response schema class |
| Add DB table | `backend/app/models/models.py` | Define SQLAlchemy ORM class + Base inheritance |
| Add React component | `frontend/src/components/` | Create .tsx file with React.FC<Props> pattern |
| Modify UI styles | `frontend/src/App.css` | Single stylesheet for all components |
| Add TypeScript type | `frontend/src/types/index.ts` | Define interface for API response |
| Change timezone logic | `backend/app/utils/timezone.py` | Adelaide is UTC+9:30 (winter) / UTC+10:30 (summer) |
| Adjust data retention | `backend/app/main.py` | Search for cleanup_old_messages task (line ~200) |
| Add scheduled task | `backend/app/main.py` | In lifespan context manager, add to scheduler |

### Important Patterns

**Message Parsing** (`parser.py`)
```python
def parse(self, raw_message: str) -> Optional[ParsedMessage]:
    # Always return ParsedMessage with all fields or None if unparseable
    # Set message_type: dispatch, update, stand_down, info, etc.
    pass
```

**Database Query** (any service)
```python
async def get_incidents(self, db: AsyncSession, limit: int = 20) -> List[Incident]:
    result = await db.execute(
        select(Incident)
        .where(Incident.status == "active")
        .order_by(Incident.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()
```

**API Response** (`routes.py`)
```python
class IncidentResponse(BaseModel):
    id: int
    incident_number: str
    # ... other fields
    class Config:
        from_attributes = True  # for SQLAlchemy ORM
```

**React Component** (`components/*.tsx`)
```typescript
interface ComponentProps {
  incident: Incident;
  onSelect: (id: number) => void;
}

export const Component: React.FC<ComponentProps> = ({ incident, onSelect }) => {
  const [state, setState] = useState(false);
  const handler = useCallback(() => { setState(!state); }, [state]);
  return <div onClick={handler}>...</div>;
};
```

### Frontend State Flow

- **App.tsx**: Owns incidents[], selectedFilters, searchTerm
- Components use `useState` for local UI state (expanded, focused, etc)
- `useEffect` hooks subscribe to SSE stream and API endpoints
- No Redux/Context API — props drilling is acceptable for this project size
