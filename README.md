# SAGRN SDR Monitor

Emergency services pager monitoring system for South Australia. Monitors the SAGRN (South Australian Government Radio Network) for emergency messages and displays them on a web interface.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Raspberry Pi   │────▶│  Backend API    │────▶│  Web Frontend   │
│  (RTL-SDR +     │     │  (FastAPI)      │     │  (React)        │
│   multimon-ng)  │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  SQLite DB      │
                        │  + CFS Feed     │
                        └─────────────────┘
```

## Quick Start

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
mkdir data

# Run the server
python run.py
```

The API will be available at http://localhost:8000

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

The frontend will be available at http://localhost:3000

### 3. Import Historical Logs

```bash
cd scripts
python import_logs.py ../pager_log.txt
```

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

Update `SAGRN_SERVER_URL` to your server's IP address.

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

- `DATABASE_URL` - Database connection string
- `MESSAGE_RETENTION_DAYS` - Days to keep messages (default: 30)
- `GEOCODE_RATE_LIMIT` - Nominatim rate limit (default: 1/sec)

## Features

- Real-time pager message monitoring
- Multi-agency support (SAAS, CFS, MFS, SES, MedStar)
- Automatic geocoding with Nominatim
- CFS incident feed integration
- Incident grouping and unit tracking
- Web interface similar to sapaging.com
- 30-day message retention
