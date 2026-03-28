"""Process monitoring — find CPU hogs, stale processes, and zombies."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import psutil


@dataclass
class ProcInfo:
    """Snapshot of a single process."""

    pid: int
    name: str
    cpu_percent: float
    memory_mb: float
    status: str
    username: str
    create_time: float  # unix timestamp
    cmdline: str
    num_threads: int

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.create_time

    @property
    def uptime_human(self) -> str:
        secs = self.uptime_seconds
        if secs < 60:
            return f"{secs:.0f}s"
        mins = secs / 60
        if mins < 60:
            return f"{mins:.0f}m"
        hours = mins / 60
        if hours < 24:
            return f"{hours:.1f}h"
        days = hours / 24
        return f"{days:.1f}d"


@dataclass
class SystemSnapshot:
    """Overall CPU/memory state."""

    cpu_percent: float  # aggregate across all cores
    cpu_per_core: list[float]
    cpu_count_logical: int
    cpu_count_physical: int
    cpu_freq_mhz: float | None
    load_avg_1: float
    load_avg_5: float
    load_avg_15: float
    memory_total_mb: float
    memory_used_mb: float
    memory_percent: float
    swap_total_mb: float
    swap_used_mb: float
    swap_percent: float


def get_system_snapshot() -> SystemSnapshot:
    """Sample system-wide CPU and memory stats (takes ~1s for CPU measurement)."""
    cpu_pct = psutil.cpu_percent(interval=1)
    cpu_per_core = psutil.cpu_percent(percpu=True)
    freq = psutil.cpu_freq()
    load = psutil.getloadavg()
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    return SystemSnapshot(
        cpu_percent=cpu_pct,
        cpu_per_core=cpu_per_core,
        cpu_count_logical=psutil.cpu_count(logical=True),
        cpu_count_physical=psutil.cpu_count(logical=False),
        cpu_freq_mhz=freq.current if freq else None,
        load_avg_1=load[0],
        load_avg_5=load[1],
        load_avg_15=load[2],
        memory_total_mb=mem.total / (1024 * 1024),
        memory_used_mb=mem.used / (1024 * 1024),
        memory_percent=mem.percent,
        swap_total_mb=swap.total / (1024 * 1024),
        swap_used_mb=swap.used / (1024 * 1024),
        swap_percent=swap.percent,
    )


def get_all_procs() -> list[ProcInfo]:
    """Snapshot all processes with CPU/memory usage.

    Calls cpu_percent() twice with a 1s gap so the values are meaningful.
    """
    attrs = [
        "pid", "name", "cpu_percent", "memory_info", "status",
        "username", "create_time", "cmdline", "num_threads",
    ]

    # First pass primes the cpu_percent counters
    for proc in psutil.process_iter(attrs):
        pass

    time.sleep(1)

    # Second pass gets real values
    procs: list[ProcInfo] = []
    for proc in psutil.process_iter(attrs):
        try:
            info = proc.info
            mem = info.get("memory_info")
            cmdline_parts = info.get("cmdline") or []
            cmdline = " ".join(cmdline_parts)[:120] if cmdline_parts else info.get("name", "")

            procs.append(ProcInfo(
                pid=info["pid"],
                name=info.get("name") or "?",
                cpu_percent=info.get("cpu_percent") or 0.0,
                memory_mb=(mem.rss / (1024 * 1024)) if mem else 0.0,
                status=info.get("status") or "?",
                username=info.get("username") or "?",
                create_time=info.get("create_time") or 0.0,
                cmdline=cmdline,
                num_threads=info.get("num_threads") or 0,
            ))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return procs


def top_cpu(procs: list[ProcInfo], n: int = 15) -> list[ProcInfo]:
    """Return top N processes by CPU usage."""
    return sorted(procs, key=lambda p: p.cpu_percent, reverse=True)[:n]


def top_memory(procs: list[ProcInfo], n: int = 15) -> list[ProcInfo]:
    """Return top N processes by memory usage."""
    return sorted(procs, key=lambda p: p.memory_mb, reverse=True)[:n]


def find_zombies(procs: list[ProcInfo]) -> list[ProcInfo]:
    """Find zombie processes."""
    return [p for p in procs if p.status == psutil.STATUS_ZOMBIE]


def find_stale(
    procs: list[ProcInfo],
    min_hours: float = 24,
    min_cpu: float = 0.1,
    min_memory_mb: float = 10,
) -> list[ProcInfo]:
    """Find processes running for a long time with negligible CPU.

    These are candidates for stale/hung processes: old, idle, and using memory.
    Excludes system daemons, common background services, and tiny processes.
    """
    min_age = min_hours * 3600
    now = time.time()

    # Common macOS background processes that are expected to be long-running
    ignore_names = {
        "launchd", "kernel_task", "WindowServer", "loginwindow",
        "Finder", "Dock", "SystemUIServer", "mds", "mds_stores",
        "mdworker", "mdworker_shared", "distnoted", "cfprefsd",
        "lsd", "trustd", "corebrightnessd", "thermalmonitord",
        "syslogd", "notifyd", "opendirectoryd", "coreauthd",
        "coreservicesd", "fseventsd", "securityd", "CommCenter",
        "bluetoothd", "airportd", "wifid", "UserEventAgent",
        "logd", "sharingd", "rapportd", "filecoordinationd",
        "timed", "containermanagerd", "remoted", "symptomsd",
        "powerd", "configd", "locationd",
    }

    # System paths — processes launched from here are managed by macOS
    system_prefixes = (
        "/System/Library/",
        "/usr/libexec/",
        "/usr/sbin/",
        "/Library/Apple/",
        "/System/Applications/",
        "/Library/Application Support/CrashReporter/",
    )

    stale: list[ProcInfo] = []
    for p in procs:
        if p.name in ignore_names:
            continue
        if p.cmdline and any(p.cmdline.startswith(pfx) for pfx in system_prefixes):
            continue
        age = now - p.create_time
        if age >= min_age and p.cpu_percent <= min_cpu and p.memory_mb >= min_memory_mb:
            stale.append(p)

    return sorted(stale, key=lambda p: p.create_time)
