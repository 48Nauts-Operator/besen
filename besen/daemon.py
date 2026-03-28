"""Daemon management — install/uninstall/status of launchd service."""

from __future__ import annotations

import plistlib
import shutil
import subprocess
from pathlib import Path

from besen.config import HOME


LABEL = "com.besen.watch"
PLIST_DIR = HOME / "Library" / "LaunchAgents"
PLIST_PATH = PLIST_DIR / f"{LABEL}.plist"
LOG_DIR = HOME / ".config" / "besen" / "logs"
LOG_OUT = LOG_DIR / "watch.log"
LOG_ERR = LOG_DIR / "watch.err"


def _find_besen_bin() -> str:
    """Find the besen executable path."""
    result = subprocess.run(
        ["which", "besen"], capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    # Fallback: try common locations
    for candidate in [
        HOME / ".local/bin/besen",
        Path("/opt/homebrew/bin/besen"),
        HOME / ".pyenv/shims/besen",
    ]:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(
        "Cannot find 'besen' executable. Is it installed? (pip install -e .)"
    )


def build_plist(interval_minutes: int = 60) -> dict:
    """Build the launchd plist configuration.

    Runs `besen watch` at the given interval.
    """
    besen_bin = _find_besen_bin()

    return {
        "Label": LABEL,
        "ProgramArguments": [besen_bin, "watch"],
        "StartInterval": interval_minutes * 60,
        "StandardOutPath": str(LOG_OUT),
        "StandardErrorPath": str(LOG_ERR),
        "RunAtLoad": False,  # Don't run immediately on install
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "HOME": str(HOME),
        },
    }


def install(interval_minutes: int = 60) -> str:
    """Install the launchd plist and load it.

    Returns a status message.
    """
    # Unload first if already installed
    if PLIST_PATH.exists():
        uninstall(quiet=True)

    # Create log directory
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Write plist
    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    plist_data = build_plist(interval_minutes)
    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(plist_data, f)

    # Load the agent
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return f"Plist written but launchctl load failed: {result.stderr.strip()}"

    return (
        f"Installed: {PLIST_PATH}\n"
        f"Interval: every {interval_minutes} minutes\n"
        f"Logs: {LOG_DIR}\n"
        f"Run 'besen daemon status' to verify."
    )


def uninstall(quiet: bool = False) -> str:
    """Unload and remove the launchd plist.

    Returns a status message.
    """
    if not PLIST_PATH.exists():
        return "Not installed." if not quiet else ""

    subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True,
    )
    PLIST_PATH.unlink(missing_ok=True)

    return f"Uninstalled: {PLIST_PATH}"


def status() -> dict:
    """Check if the daemon is installed and running.

    Returns dict with: installed, running, interval_min, last_log, plist_path.
    """
    info = {
        "installed": PLIST_PATH.exists(),
        "running": False,
        "interval_min": 0,
        "last_log": "",
        "plist_path": str(PLIST_PATH),
        "log_path": str(LOG_OUT),
    }

    if not info["installed"]:
        return info

    # Read plist for interval
    try:
        with open(PLIST_PATH, "rb") as f:
            plist = plistlib.load(f)
        info["interval_min"] = plist.get("StartInterval", 0) // 60
    except Exception:
        pass

    # Check if loaded in launchctl
    result = subprocess.run(
        ["launchctl", "list", LABEL],
        capture_output=True, text=True,
    )
    info["running"] = result.returncode == 0

    # Read last few lines of log
    if LOG_OUT.exists():
        try:
            lines = LOG_OUT.read_text().strip().splitlines()
            info["last_log"] = "\n".join(lines[-5:]) if lines else "(empty)"
        except OSError:
            info["last_log"] = "(unreadable)"

    return info


def read_logs(lines: int = 30) -> str:
    """Read the last N lines of the watch log."""
    if not LOG_OUT.exists():
        return "(no log file yet — daemon hasn't run)"

    try:
        all_lines = LOG_OUT.read_text().strip().splitlines()
        return "\n".join(all_lines[-lines:]) if all_lines else "(empty)"
    except OSError as e:
        return f"(error reading log: {e})"
