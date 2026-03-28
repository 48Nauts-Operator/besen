"""Configuration and settings for Besen."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Besen runtime settings — override via env vars prefixed BESEN_."""

    # NAS mount point for the `move` command
    nas_path: Path = Path("/Volumes/Tron")

    # Directories to never touch
    protected_dirs: list[str] = [
        "Documents",
        "Desktop",
        ".ssh",
        ".gnupg",
        ".claude",
    ]

    # Size threshold (bytes) for the `big` command — default 500 MB
    big_threshold_mb: int = 500

    # Maximum depth for recursive scans
    max_scan_depth: int = 5

    # Dry-run mode (no deletions)
    dry_run: bool = False

    model_config = {"env_prefix": "BESEN_"}


settings = Settings()
HOME = Path.home()
