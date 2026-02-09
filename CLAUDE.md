# SAGRN SDR Monitor - Claude Code Reference

> Emergency services pager monitoring system for South Australia (SA Government Radio Network)
> Optimized for GCP free tier (e2-micro: 1GB RAM, 0.25 vCPU)

## Project Map

```
SAGRN Lightweight/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── api/routes.py       # API endpoints
│   │   ├── core/config.py      # Pydantic settings
│   │   ├── data/sa_suburbs.py  # SA suburb lookup data
│   │   ├── models/
│   │   │   ├── database.py     # SQLAlchemy async setup
│   │   │   └── models.py       # ORM models (Agency, Message, Incident)
│   │   ├── services/           # Business logic
│   │   │   ├── parser.py       # Message parsing
│   │   │   ├── incident_service.py
│   │   │   ├── message_combiner.py
│   │   │   ├── event_manager.py    # SSE broadcasting
│   │   │   ├── cfs_integration.py  # CFS XML feed
│   │   │   ├── waze_service.py     # Waze traffic API
│   │   │   ├── geocoder.py
│   │   │   └── suburb_matcher.py
│   │   ├── utils/timezone.py   # Adelaide timezone helpers
│   │   └── main.py             # FastAPI app, lifespan hooks
│   ├── requirements.txt
│   ├── run.py                  # Dev server entry point
│   └── .env.example
│
├── frontend/                   # React TypeScript frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── AgencyFilter.tsx
│   │   │   ├── IncidentCard.tsx
│   │   │   ├── IncidentDetail.tsx
│   │   │   ├── RawMessageCard.tsx
│   │   │   └── SearchBar.tsx
│   │   ├── services/api.ts     # API client + SSE subscription
│   │   ├── types/index.ts      # TypeScript interfaces
│   │   ├── App.tsx             # Main component, state management
│   │   └── App.css             # All styles (single file)
│   ├── package.json
│   └── tsconfig.json
│
├── scripts/                    # Deployment & utilities
│   ├── install_gcp_debian.sh   # GCP one-command setup
│   ├── install_raspberrypi.sh  # Pi installation
│   ├── update_gcp.sh           # Update existing deployment
│   ├── preflight_check.sh      # System validation
│   ├── check_db.py             # DB inspection
│   └── import_logs.py          # Historical data import
│
└── data/sagrn.db               # SQLite database (auto-created)
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

### Production Deployment

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
| `/api/agencies` | GET | Agency list |
| `/api/stats` | GET | Dashboard stats |
| `/api/health` | GET | Health check |
| `/api/events` | GET | SSE stream |
| `/api/messages/raw` | GET | Raw messages |

## Database Schema (Key Tables)

- **agencies** - Emergency services (SAAS, CFS, MFS, SES, MedStar, TMC, WAZE)
- **messages** - Raw pager messages with parsed fields
- **incidents** - Grouped incidents by unique ID
- **incident_units** - Units assigned to incidents
- **locations** - Geocoded location cache

## Architecture Notes

### Data Flow
```
Raspberry Pi (RTL-SDR + multimon-ng)
    ↓ POST /api/collector/message
GCP VM (FastAPI + SQLite)
    ↓ Serves React static build
Browser (React UI)
    ↑ SSE /api/events
```

### Processing Pipeline
1. Messages arrive from Pi collector (FLEX protocol)
2. `MessageParser` extracts agency, location, units, type
3. `IncidentService` groups related messages
4. `MessageCombiner` deduplicates
5. `EventManager` broadcasts via SSE
6. Frontend receives and renders

### Scheduled Tasks
- **Cleanup**: Every 1 hour (24-hour retention)
- **CFS Update**: Every 5 minutes
- **Waze Update**: Every 2 minutes

### Memory Optimization (GCP Free Tier)
- Single Uvicorn worker
- SQLite (no external DB)
- Lazy loading (20 items, then "Load More")
- 24-hour message retention

## Environment Variables

```env
DATABASE_URL=sqlite+aiosqlite:///./data/sagrn.db
CFS_INCIDENTS_XML=https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_current_incidents.xml
CFS_CAP_XML=https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_cap_incidents.xml
MESSAGE_RETENTION_HOURS=24
HOST=0.0.0.0
PORT=8000
WORKERS=1
```

## Key Files for Common Tasks

| Task | Files |
|------|-------|
| Add new agency | `backend/app/services/incident_service.py` (AGENCY_CONFIG) |
| Modify parsing | `backend/app/services/parser.py` |
| Add API endpoint | `backend/app/api/routes.py` |
| Add UI component | `frontend/src/components/` |
| Modify styles | `frontend/src/App.css` |
| Add TypeScript type | `frontend/src/types/index.ts` |
| Change timezone handling | `backend/app/utils/timezone.py` |
