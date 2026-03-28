"""Mover — transfers files to NAS via rsync with verification."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from besen.config import settings

console = Console()


class MoveError(Exception):
    """Raised when a move operation fails."""


def check_nas() -> bool:
    """Check if the NAS is mounted and writable."""
    nas = settings.nas_path
    if not nas.exists():
        return False
    if not nas.is_mount():
        return False
    # Check writable
    test_file = nas / ".besen_write_test"
    try:
        test_file.touch()
        test_file.unlink()
        return True
    except OSError:
        return False


def move_to_nas(
    source: Path,
    dest_subdir: str = "",
    *,
    dry_run: bool | None = None,
    delete_source: bool = False,
) -> bool:
    """Move a file or directory to NAS using rsync.

    Args:
        source: File or directory to move.
        dest_subdir: Subdirectory under NAS root (created if needed).
        dry_run: If True, only show what would happen.
        delete_source: If True, remove source after verified transfer.

    Returns:
        True if transfer succeeded.
    """
    is_dry = dry_run if dry_run is not None else settings.dry_run
    dest = settings.nas_path / dest_subdir if dest_subdir else settings.nas_path

    if not check_nas():
        raise MoveError(f"NAS not available at {settings.nas_path}")

    # Ensure destination directory exists
    if not is_dry:
        dest.mkdir(parents=True, exist_ok=True)

    # Build rsync command
    cmd = [
        "rsync",
        "-avh",
        "--progress",
    ]
    if is_dry:
        cmd.append("--dry-run")

    # Trailing slash on dirs means "copy contents"
    src_str = f"{source}/" if source.is_dir() else str(source)
    cmd.extend([src_str, str(dest) + "/"])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour max
        )

        if result.returncode != 0:
            console.print(f"[red]rsync error:[/red] {result.stderr.strip()}")
            return False

        # Verify transfer (check destination exists and has size)
        if not is_dry:
            dest_path = dest / source.name if source.is_file() else dest
            if not dest_path.exists():
                console.print("[red]Verification failed: destination not found[/red]")
                return False

            # Delete source if requested and verified
            if delete_source:
                if source.is_dir():
                    import shutil

                    shutil.rmtree(source)
                else:
                    source.unlink()
                console.print(f"  [green]✓[/green] Source removed: {source}")

        return True

    except subprocess.TimeoutExpired:
        console.print("[red]Transfer timed out after 1 hour[/red]")
        return False
    except FileNotFoundError:
        console.print("[red]rsync not found — install with: brew install rsync[/red]")
        return False
