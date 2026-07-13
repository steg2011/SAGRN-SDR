"""SAGRN Admin Dashboard.

Runs as its own container (see docker-compose.yml `admin` service) so the
Docker socket and host /proc mounts are never exposed to the public backend.
Served at admin.sagrn.tmc-sa.org via the Cloudflare tunnel.
"""
import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from app.admin import auth, docker_client, system_stats
from app.models.database import async_session
from app.models.models import Message, Visit

TEMPLATES = Path(__file__).parent / "templates"
COLLECTOR_LOG_DIR = Path(os.environ.get("COLLECTOR_LOG_DIR", "/collector/logs"))

app = FastAPI(title="SAGRN Admin", docs_url=None, redoc_url=None, openapi_url=None)


def require_auth(request: Request) -> None:
    if not auth.is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")


# ---------------------------------------------------------------- auth pages

class LoginInput(BaseModel):
    password: str


@app.get("/login")
async def login_page():
    return FileResponse(str(TEMPLATES / "login.html"))


@app.post("/api/login")
async def login(body: LoginInput, request: Request, response: Response):
    ip = auth.client_ip(request)
    if not auth.register_login_attempt(ip):
        raise HTTPException(status_code=429, detail="Too many attempts, try again later")
    if not auth.check_password(body.password):
        raise HTTPException(status_code=401, detail="Incorrect password")
    auth.clear_login_attempts(ip)
    response.set_cookie(
        auth.SESSION_COOKIE,
        auth.create_session_token(),
        max_age=auth.SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return {"ok": True}


@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(auth.SESSION_COOKIE)
    return {"ok": True}


@app.get("/")
async def dashboard(request: Request):
    if not auth.is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return FileResponse(str(TEMPLATES / "dashboard.html"))


# ------------------------------------------------------------- data helpers

def _container_summary(entry: Dict) -> Dict:
    labels = entry.get("Labels") or {}
    return {
        "id": entry.get("Id", "")[:12],
        "name": (entry.get("Names") or ["?"])[0].lstrip("/"),
        "service": labels.get("com.docker.compose.service"),
        "image": entry.get("Image"),
        "state": entry.get("State"),
        "status": entry.get("Status"),
    }


async def _container_with_stats(entry: Dict) -> Dict:
    summary = _container_summary(entry)
    if entry.get("State") == "running":
        stats = await docker_client.container_stats(entry["Id"])
        if stats:
            summary["cpu_percent"] = docker_client.cpu_percent_from_stats(stats)
            summary["memory"] = docker_client.memory_from_stats(stats)
    inspect = await docker_client.inspect_container(entry["Id"])
    if inspect:
        state = inspect.get("State", {})
        summary["restart_count"] = inspect.get("RestartCount", 0)
        summary["started_at"] = state.get("StartedAt")
        health = state.get("Health")
        summary["health"] = health.get("Status") if health else None
    return summary


def _collector_env(inspect: Dict) -> Dict[str, str]:
    env_list = (inspect.get("Config") or {}).get("Env") or []
    env = dict(item.split("=", 1) for item in env_list if "=" in item)
    return {
        "collector_id": env.get("COLLECTOR_ID"),
        "frequency": env.get("PAGER_FREQUENCY"),
        "gain": env.get("SAGRN_GAIN"),
        "sdr_timeout_seconds": env.get("SAGRN_SDR_TIMEOUT"),
    }


async def _message_throughput() -> Dict:
    now = datetime.utcnow()
    async with async_session() as db:
        last = await db.execute(
            select(func.max(Message.received_at))
        )
        last_received = last.scalar()
        hour = await db.execute(
            select(func.count(Message.id)).where(
                Message.received_at >= now - timedelta(hours=1)
            )
        )
        day = await db.execute(
            select(func.count(Message.id)).where(
                Message.received_at >= now - timedelta(hours=24)
            )
        )
    return {
        "last_message_at": last_received.isoformat() if last_received else None,
        "last_message_age_seconds": (
            (now - last_received).total_seconds() if last_received else None
        ),
        "messages_last_hour": hour.scalar(),
        "messages_last_24h": day.scalar(),
    }


def _collector_log_info() -> Dict:
    info: Dict = {"log_dir_bytes": 0, "today_log_bytes": 0, "recent_lines": []}
    try:
        files = sorted(COLLECTOR_LOG_DIR.glob("*.txt"))
        info["log_dir_bytes"] = sum(f.stat().st_size for f in files)
        if files:
            latest = files[-1]
            info["today_log_bytes"] = latest.stat().st_size
            with open(latest, "r", encoding="utf-8", errors="replace") as f:
                info["recent_lines"] = f.readlines()[-8:]
            info["recent_lines"] = [line.rstrip("\n") for line in info["recent_lines"]]
    except OSError:
        pass
    return info


async def _sdr_details(containers: List[Dict]) -> Dict:
    details: Dict = {"container_state": None}
    collector = next(
        (
            c for c in containers
            if (c.get("Labels") or {}).get("com.docker.compose.service") == "collector"
        ),
        None,
    )
    if collector:
        details["container_state"] = collector.get("State")
        details["container_status"] = collector.get("Status")
        inspect = await docker_client.inspect_container(collector["Id"])
        if inspect:
            details.update(_collector_env(inspect))
            details["restart_count"] = inspect.get("RestartCount", 0)
    details.update(await _message_throughput())
    details["logs"] = _collector_log_info()
    return details


# ------------------------------------------------------------ API endpoints

@app.get("/api/overview")
async def overview(request: Request):
    require_auth(request)
    host_task = asyncio.create_task(system_stats.snapshot())
    containers_raw = await docker_client.list_containers()
    container_tasks = [_container_with_stats(c) for c in containers_raw]
    sdr_task = asyncio.create_task(_sdr_details(containers_raw))
    containers = list(await asyncio.gather(*container_tasks))
    containers.sort(key=lambda c: (c["state"] != "running", c["name"]))
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "host": await host_task,
        "containers": containers,
        "sdr": await sdr_task,
    }


@app.get("/api/faults")
async def faults(request: Request, tail: int = Query(300, le=2000)):
    require_auth(request)
    containers = await docker_client.list_containers()
    results: List[Dict] = []

    async def scan(entry: Dict):
        service = (entry.get("Labels") or {}).get(
            "com.docker.compose.service"
        ) or (entry.get("Names") or ["?"])[0].lstrip("/")
        lines = await docker_client.container_logs(entry["Id"], tail=tail)
        for line in docker_client.extract_faults(lines, limit=40):
            results.append({"container": service, "line": line[:500]})

    await asyncio.gather(*(scan(c) for c in containers))
    # Docker timestamps prefix each line (RFC3339), so sorting on line works
    results.sort(key=lambda r: r["line"], reverse=True)
    return {"faults": results[:120]}


@app.get("/api/logs")
async def logs(
    request: Request,
    container: str = Query(..., max_length=64),
    tail: int = Query(200, le=1000),
):
    require_auth(request)
    containers = await docker_client.list_containers()
    match = next(
        (
            c for c in containers
            if (c.get("Labels") or {}).get("com.docker.compose.service") == container
            or (c.get("Names") or ["?"])[0].lstrip("/") == container
        ),
        None,
    )
    if not match:
        raise HTTPException(status_code=404, detail="Container not found")
    lines = await docker_client.container_logs(match["Id"], tail=tail)
    return {"container": container, "lines": lines}


@app.get("/api/visitors")
async def visitors(request: Request):
    require_auth(request)
    now = datetime.utcnow()
    async with async_session() as db:
        recent = await db.execute(
            select(Visit).order_by(Visit.visited_at.desc()).limit(100)
        )
        recent_visits = recent.scalars().all()

        day_counts = await db.execute(
            select(func.date(Visit.visited_at), func.count(Visit.id))
            .where(Visit.visited_at >= now - timedelta(days=14))
            .group_by(func.date(Visit.visited_at))
            .order_by(func.date(Visit.visited_at))
        )
        unique_24h = await db.execute(
            select(func.count(func.distinct(Visit.ip))).where(
                Visit.visited_at >= now - timedelta(hours=24)
            )
        )
        total_24h = await db.execute(
            select(func.count(Visit.id)).where(
                Visit.visited_at >= now - timedelta(hours=24)
            )
        )
        total_7d = await db.execute(
            select(func.count(Visit.id)).where(
                Visit.visited_at >= now - timedelta(days=7)
            )
        )
        countries = await db.execute(
            select(Visit.country, func.count(Visit.id))
            .where(Visit.visited_at >= now - timedelta(days=7))
            .group_by(Visit.country)
            .order_by(func.count(Visit.id).desc())
            .limit(10)
        )
    return {
        "visits_24h": total_24h.scalar(),
        "unique_visitors_24h": unique_24h.scalar(),
        "visits_7d": total_7d.scalar(),
        "per_day": [
            {"date": str(day), "count": count} for day, count in day_counts.all()
        ],
        "top_countries_7d": [
            {"country": country or "??", "count": count}
            for country, count in countries.all()
        ],
        "recent": [
            {
                "visited_at": v.visited_at.isoformat() if v.visited_at else None,
                "ip": v.ip,
                "country": v.country,
                "path": v.path,
                "user_agent": v.user_agent,
            }
            for v in recent_visits
        ],
    }


@app.get("/api/health")
async def health():
    return {"status": "ok"}
