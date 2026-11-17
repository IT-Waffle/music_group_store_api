import asyncio
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.domain.system.schemas import CapacityMetrics, CpuMetrics, SystemMetrics


def _percentage(used: int | float, total: int | float) -> float:
    if total <= 0:
        return 0.0
    return round(max(0.0, min(100.0, used / total * 100)), 1)


def _read_cpu_snapshot(proc_root: Path) -> tuple[int, int]:
    values = (proc_root / "stat").read_text(encoding="utf-8").splitlines()[0].split()
    if not values or values[0] != "cpu" or len(values) < 6:
        raise RuntimeError("Invalid procfs CPU statistics")

    counters = [int(value) for value in values[1:9]]
    total = sum(counters)
    idle = counters[3] + counters[4]
    return total, idle


def _calculate_cpu_usage(before: tuple[int, int], after: tuple[int, int]) -> float:
    total_delta = after[0] - before[0]
    idle_delta = after[1] - before[1]
    if total_delta <= 0:
        return 0.0
    return _percentage(total_delta - idle_delta, total_delta)


def _read_meminfo(proc_root: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in (proc_root / "meminfo").read_text(encoding="utf-8").splitlines():
        key, separator, raw_value = line.partition(":")
        if not separator:
            continue
        parts = raw_value.strip().split()
        if parts:
            values[key] = int(parts[0]) * 1024
    return values


def _capacity(total: int, available: int) -> CapacityMetrics:
    safe_total = max(0, total)
    safe_available = max(0, min(available, safe_total))
    used = safe_total - safe_available
    return CapacityMetrics(
        total_bytes=safe_total,
        used_bytes=used,
        available_bytes=safe_available,
        usage_percent=_percentage(used, safe_total),
    )


def _resolve_proc_root() -> Path:
    configured = settings.HOST_PROC_ROOT
    if (configured / "stat").is_file():
        return configured
    fallback = Path("/proc")
    if (fallback / "stat").is_file():
        return fallback
    raise RuntimeError("Linux procfs is unavailable")


async def collect_system_metrics() -> SystemMetrics:
    proc_root = _resolve_proc_root()
    before = _read_cpu_snapshot(proc_root)
    await asyncio.sleep(0.15)
    after = _read_cpu_snapshot(proc_root)

    meminfo = _read_meminfo(proc_root)
    memory_total = meminfo.get("MemTotal", 0)
    memory_available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
    swap_total = meminfo.get("SwapTotal", 0)
    swap_free = meminfo.get("SwapFree", 0)

    load_parts = (proc_root / "loadavg").read_text(encoding="utf-8").split()
    uptime = float((proc_root / "uptime").read_text(encoding="utf-8").split()[0])
    cpuinfo = (proc_root / "cpuinfo").read_text(encoding="utf-8")
    cores = sum(line.startswith("processor") for line in cpuinfo.splitlines())
    disk = shutil.disk_usage("/")

    return SystemMetrics(
        observed_at=datetime.now(UTC),
        uptime_seconds=max(0, int(uptime)),
        cpu=CpuMetrics(
            usage_percent=_calculate_cpu_usage(before, after),
            cores=max(1, cores or os.cpu_count() or 1),
            load_1m=max(0.0, float(load_parts[0])),
            load_5m=max(0.0, float(load_parts[1])),
            load_15m=max(0.0, float(load_parts[2])),
        ),
        memory=_capacity(memory_total, memory_available),
        swap=_capacity(swap_total, swap_free),
        disk=_capacity(disk.total, disk.free),
    )
