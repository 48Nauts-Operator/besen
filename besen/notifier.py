"""macOS native notifications via osascript."""

from __future__ import annotations

import subprocess


SOUND_DEFAULT = "default"
SOUND_NONE = ""

APP_TITLE = "Besen"


def notify(
    title: str,
    message: str,
    subtitle: str = "",
    sound: str = SOUND_DEFAULT,
) -> bool:
    """Send a macOS notification center alert.

    Uses osascript (AppleScript) — zero dependencies, works on every Mac.
    Returns True if the notification was sent successfully.
    """
    # Build the AppleScript display notification command
    parts = [f'display notification "{_escape(message)}"']
    parts.append(f'with title "{_escape(APP_TITLE)}"')
    if subtitle:
        parts.append(f'subtitle "{_escape(subtitle)}"')
    if title and title != APP_TITLE:
        # Use subtitle for the section name, title is always "Besen"
        if not subtitle:
            parts.append(f'subtitle "{_escape(title)}"')
    if sound:
        parts.append(f'sound name "{sound}"')

    script = " ".join(parts)

    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def notify_disk_low(free_gb: float, threshold_gb: float, mount: str = "/") -> bool:
    """Notify when disk space is below threshold."""
    return notify(
        title="Disk Space Low",
        message=f"{free_gb:.1f} GB free on {mount} (threshold: {threshold_gb:.0f} GB)",
        subtitle="Run: besen sweep",
    )


def notify_zombies(count: int) -> bool:
    """Notify about zombie processes."""
    return notify(
        title="Zombie Processes",
        message=f"{count} zombie process{'es' if count != 1 else ''} detected",
        subtitle="Run: besen cpu --kill --zombie",
    )


def notify_high_cpu(process_name: str, cpu_pct: float, duration_min: int) -> bool:
    """Notify about a process with sustained high CPU."""
    return notify(
        title="High CPU Usage",
        message=f"{process_name} at {cpu_pct:.0f}% CPU for {duration_min}+ min",
        subtitle="Check: besen cpu",
    )


def notify_memory_pressure(mem_pct: float) -> bool:
    """Notify about high memory usage."""
    return notify(
        title="Memory Pressure",
        message=f"Memory at {mem_pct:.0f}% — system may slow down",
        subtitle="Check: besen cpu --memory",
    )


def notify_cleanup_done(freed_bytes: int) -> bool:
    """Notify after automatic cleanup."""
    from humanize import naturalsize

    return notify(
        title="Auto-Cleanup Complete",
        message=f"Freed {naturalsize(freed_bytes, binary=True)}",
        sound=SOUND_NONE,  # Silent for routine operations
    )


def _escape(text: str) -> str:
    """Escape special characters for AppleScript strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"')
