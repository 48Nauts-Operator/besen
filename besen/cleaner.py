"""Cleaner — safely removes files from scanned targets."""

from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console

from besen.config import settings
from besen.scanner import CleanTarget

console = Console()


def clean_target(target: CleanTarget, *, dry_run: bool | None = None) -> int:
    """Clean a single target directory.

    Returns the number of bytes freed.
    """
    is_dry = dry_run if dry_run is not None else settings.dry_run

    if not target.exists or target.size_bytes == 0:
        return 0

    path = target.path
    freed = target.size_bytes

    if is_dry:
        console.print(f"  [dim]DRY RUN: would clean {path}[/dim]")
        return freed

    try:
        # Delete contents, not the directory itself
        for child in path.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except (PermissionError, OSError) as e:
                console.print(f"  [yellow]Skip {child.name}: {e}[/yellow]")
                # Reduce freed estimate
                try:
                    freed -= child.stat().st_size
                except OSError:
                    pass
    except (PermissionError, OSError) as e:
        console.print(f"  [red]Cannot access {path}: {e}[/red]")
        return 0

    return max(freed, 0)


def clean_targets(
    targets: list[CleanTarget],
    *,
    dry_run: bool | None = None,
) -> int:
    """Clean multiple targets. Returns total bytes freed."""
    total_freed = 0
    for target in targets:
        freed = clean_target(target, dry_run=dry_run)
        if freed > 0:
            from humanize import naturalsize

            label = "[dim](dry)[/dim] " if (dry_run or settings.dry_run) else ""
            console.print(
                f"  {label}[green]✓[/green] {target.name}: "
                f"{naturalsize(freed, binary=True)} freed"
            )
            total_freed += freed
    return total_freed
