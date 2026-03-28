"""Auto-policies — rules for automatic cleanup and process management."""

from __future__ import annotations

import json
import signal
from dataclasses import asdict, dataclass, field
from pathlib import Path

import psutil

from besen.config import HOME


# ── Policy definitions ────────────────────────────────────────────────

CONFIG_PATH = HOME / ".config" / "besen" / "policies.json"


@dataclass
class DiskPolicy:
    """When to auto-clean disk space."""

    enabled: bool = True
    # Trigger cleanup when free space drops below this (GB)
    free_threshold_gb: float = 50.0
    # Only auto-clean targets marked safe_to_clean
    safe_only: bool = True
    # Notify when free space is below this (GB) — even without cleaning
    notify_threshold_gb: float = 100.0


@dataclass
class ZombiePolicy:
    """When to auto-kill zombie processes."""

    enabled: bool = True
    # Auto-kill zombies older than this (hours)
    min_age_hours: float = 1.0
    # Notify about new zombies
    notify: bool = True


@dataclass
class CpuPolicy:
    """When to alert about CPU issues."""

    enabled: bool = True
    # Notify if a process exceeds this CPU% for sustained_minutes
    high_cpu_threshold: float = 200.0
    sustained_minutes: int = 10
    # Notify about memory pressure above this %
    memory_threshold: float = 90.0
    # Auto-kill stale user processes older than this (hours, 0 = disabled)
    auto_kill_stale_hours: float = 0  # Disabled by default — opt-in


@dataclass
class Policies:
    """All auto-policies."""

    disk: DiskPolicy = field(default_factory=DiskPolicy)
    zombie: ZombiePolicy = field(default_factory=ZombiePolicy)
    cpu: CpuPolicy = field(default_factory=CpuPolicy)


def load_policies() -> Policies:
    """Load policies from config file, or return defaults."""
    if not CONFIG_PATH.exists():
        return Policies()

    try:
        data = json.loads(CONFIG_PATH.read_text())
        return Policies(
            disk=DiskPolicy(**data.get("disk", {})),
            zombie=ZombiePolicy(**data.get("zombie", {})),
            cpu=CpuPolicy(**data.get("cpu", {})),
        )
    except (json.JSONDecodeError, TypeError, KeyError):
        return Policies()


def save_policies(policies: Policies) -> None:
    """Save policies to config file."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "disk": asdict(policies.disk),
        "zombie": asdict(policies.zombie),
        "cpu": asdict(policies.cpu),
    }
    CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n")


# ── Policy execution ─────────────────────────────────────────────────


def apply_disk_policy(policies: Policies) -> dict:
    """Check disk space and auto-clean if needed.

    Returns a summary dict with keys: checked, notified, cleaned, freed_bytes.
    """
    from besen.cleaner import clean_targets
    from besen.notifier import notify_cleanup_done, notify_disk_low
    from besen.scanner import get_disk_usage, scan_targets

    result = {"checked": True, "notified": False, "cleaned": False, "freed_bytes": 0}
    dp = policies.disk
    if not dp.enabled:
        result["checked"] = False
        return result

    usage = get_disk_usage()
    boot = next((v for v in usage["volumes"] if v["mount"] == "/"), None)
    if not boot:
        return result

    free_gb = boot["free"] / (1024 ** 3)

    # Notify if below notify threshold
    if free_gb < dp.notify_threshold_gb:
        notify_disk_low(free_gb, dp.notify_threshold_gb)
        result["notified"] = True

    # Auto-clean if below free threshold
    if free_gb < dp.free_threshold_gb:
        targets = scan_targets()
        cleanable = [
            t for t in targets
            if t.exists and t.size_bytes > 0 and (t.safe_to_clean if dp.safe_only else True)
        ]
        cleanable.sort(key=lambda t: t.size_bytes, reverse=True)

        if cleanable:
            freed = clean_targets(cleanable, dry_run=False)
            result["cleaned"] = True
            result["freed_bytes"] = freed
            if freed > 0:
                notify_cleanup_done(freed)

    return result


def apply_zombie_policy(policies: Policies) -> dict:
    """Check for and optionally kill zombie processes.

    Returns: checked, count, killed.
    """
    import time

    from besen.notifier import notify_zombies
    from besen.procs import find_zombies, get_all_procs

    result = {"checked": True, "count": 0, "killed": 0}
    zp = policies.zombie
    if not zp.enabled:
        result["checked"] = False
        return result

    procs = get_all_procs()
    zombies = find_zombies(procs)
    result["count"] = len(zombies)

    if not zombies:
        return result

    # Notify
    if zp.notify:
        notify_zombies(len(zombies))

    # Kill zombies older than min_age
    now = time.time()
    for z in zombies:
        age_hours = (now - z.create_time) / 3600
        if age_hours >= zp.min_age_hours:
            try:
                psutil.Process(z.pid).send_signal(signal.SIGKILL)
                result["killed"] += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    return result


def apply_cpu_policy(policies: Policies) -> dict:
    """Check CPU/memory health and notify.

    Returns: checked, high_cpu_procs, memory_alert.
    """
    from besen.notifier import notify_high_cpu, notify_memory_pressure
    from besen.procs import get_all_procs, get_system_snapshot

    result = {"checked": True, "high_cpu_procs": [], "memory_alert": False}
    cp = policies.cpu
    if not cp.enabled:
        result["checked"] = False
        return result

    snap = get_system_snapshot()

    # Memory pressure
    if snap.memory_percent >= cp.memory_threshold:
        notify_memory_pressure(snap.memory_percent)
        result["memory_alert"] = True

    # High CPU processes
    procs = get_all_procs()
    for p in procs:
        if p.cpu_percent >= cp.high_cpu_threshold:
            notify_high_cpu(p.name, p.cpu_percent, cp.sustained_minutes)
            result["high_cpu_procs"].append(p.name)

    return result
