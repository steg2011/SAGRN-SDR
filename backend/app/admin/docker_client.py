"""Minimal async Docker Engine API client over the unix socket.

Uses httpx's unix-domain-socket transport (httpx is already a project
dependency) so we don't need the docker SDK. The socket is mounted
read-only into the admin container and only GET endpoints are used.
"""
import re
from typing import Dict, List, Optional

import httpx

DOCKER_SOCK = "/var/run/docker.sock"

FAULT_PATTERN = re.compile(
    r"\b(error|critical|exception|traceback|fatal|failed|failure|panic|warn(?:ing)?)\b",
    re.IGNORECASE,
)


def _client() -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(uds=DOCKER_SOCK)
    return httpx.AsyncClient(transport=transport, base_url="http://docker", timeout=20.0)


async def list_containers() -> List[Dict]:
    async with _client() as client:
        resp = await client.get("/containers/json", params={"all": "1"})
        resp.raise_for_status()
        return resp.json()


async def inspect_container(container_id: str) -> Optional[Dict]:
    async with _client() as client:
        resp = await client.get(f"/containers/{container_id}/json")
        if resp.status_code != 200:
            return None
        return resp.json()


async def container_stats(container_id: str) -> Optional[Dict]:
    """One stats sample (docker takes ~1s to compute CPU deltas)."""
    async with _client() as client:
        resp = await client.get(
            f"/containers/{container_id}/stats", params={"stream": "false"}
        )
        if resp.status_code != 200:
            return None
        return resp.json()


def cpu_percent_from_stats(stats: Dict) -> Optional[float]:
    try:
        cpu = stats["cpu_stats"]
        precpu = stats["precpu_stats"]
        cpu_delta = cpu["cpu_usage"]["total_usage"] - precpu["cpu_usage"]["total_usage"]
        system_delta = cpu.get("system_cpu_usage", 0) - precpu.get("system_cpu_usage", 0)
        online_cpus = cpu.get("online_cpus") or len(
            cpu["cpu_usage"].get("percpu_usage") or [1]
        )
        if system_delta <= 0 or cpu_delta < 0:
            return 0.0
        return round((cpu_delta / system_delta) * online_cpus * 100.0, 1)
    except (KeyError, TypeError, ZeroDivisionError):
        return None


def memory_from_stats(stats: Dict) -> Optional[Dict[str, int]]:
    try:
        mem = stats["memory_stats"]
        usage = mem["usage"] - mem.get("stats", {}).get("inactive_file", 0)
        return {"used_bytes": max(usage, 0), "limit_bytes": mem.get("limit", 0)}
    except (KeyError, TypeError):
        return None


def _demux_log_stream(raw: bytes) -> List[str]:
    """Parse docker's multiplexed log stream (8-byte frame headers)."""
    lines: List[bytes] = []
    offset = 0
    while offset + 8 <= len(raw):
        stream_type = raw[offset]
        if stream_type not in (0, 1, 2):
            # Not a multiplexed stream (TTY container) - treat as plain text
            return raw.decode("utf-8", errors="replace").splitlines()
        length = int.from_bytes(raw[offset + 4:offset + 8], "big")
        payload = raw[offset + 8:offset + 8 + length]
        lines.append(payload)
        offset += 8 + length
    return b"".join(lines).decode("utf-8", errors="replace").splitlines()


async def container_logs(
    container_id: str, tail: int = 200, timestamps: bool = True
) -> List[str]:
    async with _client() as client:
        resp = await client.get(
            f"/containers/{container_id}/logs",
            params={
                "stdout": "1",
                "stderr": "1",
                "tail": str(tail),
                "timestamps": "1" if timestamps else "0",
            },
        )
        if resp.status_code != 200:
            return []
        return _demux_log_stream(resp.content)


def extract_faults(lines: List[str], limit: int = 50) -> List[str]:
    """Return the most recent log lines that look like errors/warnings."""
    matches = [line for line in lines if FAULT_PATTERN.search(line)]
    return matches[-limit:]
