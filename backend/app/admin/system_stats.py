"""Host system statistics read from the host's /proc and /sys.

The admin container mounts the host's /proc at HOST_PROC (and /sys at
HOST_SYS) read-only, so these numbers describe the NUC itself rather than
the container. Falls back to the container's own /proc when the mounts are
absent (local development).
"""
import asyncio
import os
from pathlib import Path
from typing import Dict, List, Optional

PROC = Path(os.environ.get("HOST_PROC", "/proc"))
SYS = Path(os.environ.get("HOST_SYS", "/sys"))
# Any file residing on the host root filesystem works for statvfs()
DISK_PROBE = os.environ.get("HOST_DISK_PROBE", "/")


def _read_cpu_times() -> List[int]:
    line = (PROC / "stat").read_text().splitlines()[0]
    return [int(v) for v in line.split()[1:]]


async def cpu_percent(sample_seconds: float = 0.5) -> float:
    """Overall CPU utilisation percentage from two /proc/stat samples."""
    first = _read_cpu_times()
    await asyncio.sleep(sample_seconds)
    second = _read_cpu_times()
    deltas = [b - a for a, b in zip(first, second)]
    total = sum(deltas)
    if total <= 0:
        return 0.0
    idle = deltas[3] + (deltas[4] if len(deltas) > 4 else 0)  # idle + iowait
    return round(100.0 * (total - idle) / total, 1)


def cpu_count() -> int:
    return sum(
        1 for line in (PROC / "stat").read_text().splitlines()
        if line.startswith("cpu") and line[3:4].isdigit()
    )


def memory() -> Dict[str, int]:
    info: Dict[str, int] = {}
    for line in (PROC / "meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        info[key] = int(rest.split()[0]) * 1024  # kB -> bytes
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", 0)
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": total - available,
        "swap_total_bytes": info.get("SwapTotal", 0),
        "swap_used_bytes": info.get("SwapTotal", 0) - info.get("SwapFree", 0),
    }


def load_average() -> List[float]:
    parts = (PROC / "loadavg").read_text().split()
    return [float(parts[0]), float(parts[1]), float(parts[2])]


def uptime_seconds() -> float:
    return float((PROC / "uptime").read_text().split()[0])


def disk_usage() -> Dict[str, int]:
    st = os.statvfs(DISK_PROBE)
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    return {"total_bytes": total, "free_bytes": free, "used_bytes": total - free}


def cpu_temperature() -> Optional[float]:
    """Best-effort CPU temperature in Celsius from thermal zones."""
    best: Optional[float] = None
    try:
        for zone in sorted(SYS.glob("class/thermal/thermal_zone*")):
            try:
                zone_type = (zone / "type").read_text().strip()
                temp = int((zone / "temp").read_text().strip()) / 1000.0
            except (OSError, ValueError):
                continue
            if not -40 < temp < 150:
                continue
            if zone_type in ("x86_pkg_temp", "cpu_thermal", "coretemp"):
                return round(temp, 1)
            best = max(best, temp) if best is not None else temp
    except OSError:
        return None
    return round(best, 1) if best is not None else None


def hostname() -> str:
    for candidate in ("/host/hostname", str(PROC / "sys/kernel/hostname")):
        try:
            return Path(candidate).read_text().strip()
        except OSError:
            continue
    return os.uname().nodename


async def snapshot() -> Dict:
    """Full host stats snapshot for the dashboard."""
    mem = memory()
    return {
        "hostname": hostname(),
        "cpu_percent": await cpu_percent(),
        "cpu_count": cpu_count(),
        "load_average": load_average(),
        "memory": mem,
        "disk": disk_usage(),
        "uptime_seconds": uptime_seconds(),
        "cpu_temperature_c": cpu_temperature(),
    }
