"""Cleanup history — append-only JSONL log for reporting."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from besen.config import HOME


HISTORY_PATH = HOME / ".config" / "besen" / "history.jsonl"


@dataclass
class CleanEvent:
    """A single cleanup event."""

    timestamp: str  # ISO format
    target: str  # target name
    category: str
    freed_bytes: int
    source: str  # "manual", "sweep", "daemon"


def log_clean(
    target_name: str,
    category: str,
    freed_bytes: int,
    source: str = "manual",
) -> None:
    """Append a cleanup event to the history log."""
    if freed_bytes <= 0:
        return

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    event = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "target": target_name,
        "category": category,
        "freed": freed_bytes,
        "source": source,
    }

    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")


def load_history(since: datetime | None = None) -> list[dict]:
    """Load all events, optionally filtered by date."""
    if not HISTORY_PATH.exists():
        return []

    events = []
    for line in HISTORY_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if since:
                event_dt = datetime.fromisoformat(event["ts"])
                if event_dt < since:
                    continue
            events.append(event)
        except (json.JSONDecodeError, KeyError):
            continue

    return events


def summarize(events: list[dict]) -> dict:
    """Summarize events into totals.

    Returns: total_freed, event_count, by_category, by_target, by_source.
    """
    total = 0
    by_category: dict[str, int] = defaultdict(int)
    by_target: dict[str, int] = defaultdict(int)
    by_source: dict[str, int] = defaultdict(int)

    for e in events:
        freed = e.get("freed", 0)
        total += freed
        by_category[e.get("category", "?")] += freed
        by_target[e.get("target", "?")] += freed
        by_source[e.get("source", "?")] += freed

    return {
        "total_freed": total,
        "event_count": len(events),
        "by_category": dict(sorted(by_category.items(), key=lambda x: -x[1])),
        "by_target": dict(sorted(by_target.items(), key=lambda x: -x[1])),
        "by_source": dict(sorted(by_source.items(), key=lambda x: -x[1])),
    }


def summarize_by_period(events: list[dict]) -> dict:
    """Group events by day, week, month, year.

    Returns dict with keys: daily, weekly, monthly, yearly.
    Each value is a list of {period, freed, count}.
    """
    daily: dict[str, dict] = defaultdict(lambda: {"freed": 0, "count": 0})
    weekly: dict[str, dict] = defaultdict(lambda: {"freed": 0, "count": 0})
    monthly: dict[str, dict] = defaultdict(lambda: {"freed": 0, "count": 0})
    yearly: dict[str, dict] = defaultdict(lambda: {"freed": 0, "count": 0})

    for e in events:
        try:
            dt = datetime.fromisoformat(e["ts"])
        except (KeyError, ValueError):
            continue

        freed = e.get("freed", 0)

        # Daily: 2026-03-28
        day_key = dt.strftime("%Y-%m-%d")
        daily[day_key]["freed"] += freed
        daily[day_key]["count"] += 1

        # Weekly: 2026-W13
        week_key = dt.strftime("%G-W%V")
        weekly[week_key]["freed"] += freed
        weekly[week_key]["count"] += 1

        # Monthly: 2026-03
        month_key = dt.strftime("%Y-%m")
        monthly[month_key]["freed"] += freed
        monthly[month_key]["count"] += 1

        # Yearly: 2026
        year_key = dt.strftime("%Y")
        yearly[year_key]["freed"] += freed
        yearly[year_key]["count"] += 1

    def to_list(d: dict) -> list[dict]:
        return [
            {"period": k, "freed": v["freed"], "count": v["count"]}
            for k, v in sorted(d.items(), reverse=True)
        ]

    return {
        "daily": to_list(daily),
        "weekly": to_list(weekly),
        "monthly": to_list(monthly),
        "yearly": to_list(yearly),
    }
