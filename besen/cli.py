"""Besen CLI — macOS disk cleanup and system health tool.

Commands:
    scan   — Scan all known cleanable locations
    space  — Filesystem overview with NAS mount status
    big    — Find large files/dirs across the disk
    clean  — Interactive cleanup by category
    move   — Move files to NAS (/Volumes/Tron) via rsync
    sweep  — Quick one-shot: scan + offer to clean top items
    cpu    — CPU usage, top processes, zombies, stale procs
    watch  — Single headless run (used by daemon)
    daemon — Install/uninstall/status of background scheduler
    notify — Send a test notification
    report — Cleanup history: day/week/month/year stats
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from humanize import naturalsize
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from besen import __version__
from besen.config import settings

app = typer.Typer(
    name="besen",
    help="macOS disk cleanup CLI — scan, clean, and move.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"besen [bold]{__version__}[/bold]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be done without making changes.",
    ),
) -> None:
    """Besen — sweep your Mac clean."""
    if dry_run:
        settings.dry_run = True


# ── scan ───────────────────────────────────────────────────────────────


@app.command()
def scan(
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="Filter by category name."
    ),
    show_empty: bool = typer.Option(
        False, "--all", "-a", help="Include locations that don't exist."
    ),
    sort_by: str = typer.Option(
        "size", "--sort", "-s", help="Sort by: size, name, category."
    ),
) -> None:
    """Scan all known cleanable locations and show their sizes."""
    from besen.scanner import Category, scan_targets

    with console.status("[bold]Scanning..."):
        targets = scan_targets()

    # Filter
    if category:
        cat_lower = category.lower()
        targets = [
            t
            for t in targets
            if cat_lower in t.category.value.lower()
        ]

    if not show_empty:
        targets = [t for t in targets if t.exists and t.size_bytes > 0]

    if not targets:
        console.print("[yellow]No cleanable locations found.[/yellow]")
        raise typer.Exit()

    # Sort
    if sort_by == "name":
        targets.sort(key=lambda t: t.name.lower())
    elif sort_by == "category":
        targets.sort(key=lambda t: (t.category.value, -t.size_bytes))
    else:
        targets.sort(key=lambda t: t.size_bytes, reverse=True)

    # Display
    table = Table(title="Cleanable Locations", show_lines=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="bold")
    table.add_column("Category", style="cyan")
    table.add_column("Size", justify="right", style="green")
    table.add_column("Items", justify="right", style="dim")
    table.add_column("Safe", justify="center", width=4)

    total_bytes = 0
    for i, t in enumerate(targets, 1):
        size_str = naturalsize(t.size_bytes, binary=True)
        safe = "[green]yes[/green]" if t.safe_to_clean else "[yellow]![/yellow]"
        table.add_row(
            str(i),
            t.name,
            t.category.value,
            size_str,
            str(t.item_count),
            safe,
        )
        total_bytes += t.size_bytes

    console.print(table)
    console.print(
        f"\n[bold]Total reclaimable:[/bold] "
        f"[green]{naturalsize(total_bytes, binary=True)}[/green] "
        f"across {len(targets)} locations"
    )


# ── space ──────────────────────────────────────────────────────────────


@app.command()
def space() -> None:
    """Show filesystem overview with NAS mount status."""
    from besen.scanner import get_disk_usage

    info = get_disk_usage()

    for vol in info["volumes"]:
        pct = vol["percent"]
        bar_filled = int(pct / 5)
        bar_empty = 20 - bar_filled
        if pct > 90:
            color = "red"
        elif pct > 75:
            color = "yellow"
        else:
            color = "green"

        bar = f"[{color}]{'█' * bar_filled}[/{color}]{'░' * bar_empty}"

        panel_content = (
            f"  {bar}  {pct:.1f}%\n\n"
            f"  Total:  {naturalsize(vol['total'], binary=True)}\n"
            f"  Used:   {naturalsize(vol['used'], binary=True)}\n"
            f"  Free:   [bold {color}]{naturalsize(vol['free'], binary=True)}[/bold {color}]"
        )

        console.print(Panel(panel_content, title=f"[bold]{vol['name']}[/bold] ({vol['mount']})"))

    # NAS status
    if info["nas_mounted"]:
        console.print(f"\n[green]●[/green] NAS mounted at [bold]{settings.nas_path}[/bold]")
    else:
        console.print(f"\n[red]●[/red] NAS not mounted at {settings.nas_path}")


# ── big ────────────────────────────────────────────────────────────────


@app.command()
def big(
    path: Path = typer.Argument(
        None, help="Directory to scan (default: home)."
    ),
    threshold: int = typer.Option(
        None, "--threshold", "-t", help="Minimum size in MB."
    ),
    limit: int = typer.Option(30, "--limit", "-l", help="Max results."),
) -> None:
    """Find large files and directories."""
    from besen.scanner import scan_large_files

    scan_path = path or Path.home()

    with console.status(f"[bold]Scanning {scan_path} for large items..."):
        results = scan_large_files(
            root=scan_path,
            threshold_mb=threshold,
            max_results=limit,
        )

    if not results:
        console.print("[green]No items above threshold found.[/green]")
        raise typer.Exit()

    table = Table(title=f"Large Items (>{threshold or settings.big_threshold_mb} MB)")
    table.add_column("#", style="dim", width=3)
    table.add_column("Path", style="bold", no_wrap=True, max_width=70)
    table.add_column("Size", justify="right", style="green")

    for i, (p, size) in enumerate(results, 1):
        # Show path relative to home if possible
        try:
            display = f"~/{p.relative_to(Path.home())}"
        except ValueError:
            display = str(p)
        table.add_row(str(i), display, naturalsize(size, binary=True))

    console.print(table)


# ── clean ──────────────────────────────────────────────────────────────


def _parse_selection(selection: str, max_num: int) -> list[int]:
    """Parse user input like '1,3,5-7' or 'all' into a list of indices (0-based)."""
    if selection.strip().lower() in ("all", "a", "*"):
        return list(range(max_num))

    indices: list[int] = []
    for part in selection.split(","):
        part = part.strip()
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            try:
                start, end = int(start_s.strip()), int(end_s.strip())
                indices.extend(range(start - 1, min(end, max_num)))
            except ValueError:
                continue
        else:
            try:
                num = int(part)
                if 1 <= num <= max_num:
                    indices.append(num - 1)
            except ValueError:
                continue
    return sorted(set(indices))


@app.command()
def clean(
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="Clean only this category."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Auto-clean all safe targets."
    ),
    pick: Optional[str] = typer.Option(
        None, "--pick", "-p",
        help="Pick items by number: '1,3,5-7' or 'all'.",
    ),
) -> None:
    """Interactive cleanup — pick individual items, a range, or all.

    Examples:
        besen clean              # interactive prompt
        besen clean -p 2,4,6     # clean items 2, 4, 6
        besen clean -p 1-5       # clean items 1 through 5
        besen clean -p all       # clean everything (with confirmation)
        besen clean -y           # auto-clean all safe items
    """
    from besen.cleaner import clean_targets
    from besen.scanner import scan_targets

    with console.status("[bold]Scanning..."):
        targets = scan_targets()

    # Only show existing targets with size
    targets = [t for t in targets if t.exists and t.size_bytes > 0]

    if category:
        cat_lower = category.lower()
        targets = [
            t
            for t in targets
            if cat_lower in t.category.value.lower()
        ]

    if not targets:
        console.print("[green]Nothing to clean![/green]")
        raise typer.Exit()

    # Sort by size descending
    targets.sort(key=lambda t: t.size_bytes, reverse=True)

    # Show the table (same as scan)
    table = Table(title="Cleanable Locations", show_lines=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="bold")
    table.add_column("Category", style="cyan")
    table.add_column("Size", justify="right", style="green")
    table.add_column("Items", justify="right", style="dim")
    table.add_column("Safe", justify="center", width=4)

    total_bytes = 0
    for i, t in enumerate(targets, 1):
        size_str = naturalsize(t.size_bytes, binary=True)
        safe = "[green]yes[/green]" if t.safe_to_clean else "[yellow]![/yellow]"
        table.add_row(str(i), t.name, t.category.value, size_str, str(t.item_count), safe)
        total_bytes += t.size_bytes

    console.print(table)
    console.print(
        f"\n[bold]Total reclaimable:[/bold] "
        f"[green]{naturalsize(total_bytes, binary=True)}[/green] "
        f"across {len(targets)} locations"
    )

    # ── Determine selection ──
    if yes:
        # Auto-mode: select only safe targets
        selected_indices = [i for i, t in enumerate(targets) if t.safe_to_clean]
        if not selected_indices:
            console.print("[yellow]No safe targets to auto-clean.[/yellow]")
            raise typer.Exit()
        safe_size = sum(targets[i].size_bytes for i in selected_indices)
        console.print(
            f"\n[bold]Auto-selecting {len(selected_indices)} safe targets "
            f"({naturalsize(safe_size, binary=True)})[/bold]"
        )
    elif pick:
        selected_indices = _parse_selection(pick, len(targets))
        if not selected_indices:
            console.print("[yellow]No valid items selected.[/yellow]")
            raise typer.Exit()
    else:
        # Interactive prompt
        console.print(
            "\n[bold]Select items to clean:[/bold]\n"
            "  Enter numbers: [cyan]1,3,5-7[/cyan]  |  "
            "[cyan]all[/cyan] for everything  |  "
            "[cyan]q[/cyan] to quit"
        )
        selection = console.input("\n[bold]> [/bold]")
        if selection.strip().lower() in ("q", "quit", "exit", ""):
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit()
        selected_indices = _parse_selection(selection, len(targets))
        if not selected_indices:
            console.print("[yellow]No valid items selected.[/yellow]")
            raise typer.Exit()

    selected = [targets[i] for i in selected_indices]

    # Show what will be cleaned
    console.print(f"\n[bold]Will clean {len(selected)} target(s):[/bold]")
    has_caution = False
    for t in selected:
        marker = ""
        if not t.safe_to_clean:
            marker = " [yellow](CAUTION)[/yellow]"
            has_caution = True
        console.print(
            f"  [green]>[/green] {t.name}: "
            f"{naturalsize(t.size_bytes, binary=True)}{marker}"
        )

    total_selected_size = sum(t.size_bytes for t in selected)
    console.print(
        f"\n  Total: [bold]{naturalsize(total_selected_size, binary=True)}[/bold]"
    )

    if has_caution:
        console.print(
            "\n  [yellow]Warning: Some targets are marked CAUTION — "
            "cleaning may affect running services.[/yellow]"
        )

    # Final confirmation
    if not yes:
        if not typer.confirm("\n  Proceed?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit()

    console.print()
    freed = clean_targets(selected, source="manual")
    console.print(
        f"\n[bold green]Done![/bold green] Freed "
        f"[bold]{naturalsize(freed, binary=True)}[/bold]"
    )


# ── move ───────────────────────────────────────────────────────────────


@app.command()
def move(
    source: Path = typer.Argument(..., help="File or directory to move."),
    dest: str = typer.Option(
        "", "--dest", "-d", help="Subdirectory on NAS."
    ),
    delete: bool = typer.Option(
        False, "--delete", help="Remove source after verified transfer."
    ),
) -> None:
    """Move files to NAS (/Volumes/Tron) via rsync."""
    from besen.mover import MoveError, check_nas, move_to_nas

    if not source.exists():
        console.print(f"[red]Source not found:[/red] {source}")
        raise typer.Exit(1)

    if not check_nas():
        console.print(
            f"[red]NAS not available at {settings.nas_path}[/red]\n"
            f"Mount it first, or set BESEN_NAS_PATH to a different location."
        )
        raise typer.Exit(1)

    size_str = ""
    if source.is_file():
        size_str = f" ({naturalsize(source.stat().st_size, binary=True)})"

    console.print(
        f"Moving [bold]{source}[/bold]{size_str} → "
        f"[bold]{settings.nas_path / dest}[/bold]"
    )

    if delete and not settings.dry_run:
        if not typer.confirm("Source will be deleted after transfer. Continue?"):
            raise typer.Exit()

    try:
        success = move_to_nas(source, dest, delete_source=delete)
        if success:
            console.print("[bold green]Transfer complete.[/bold green]")
        else:
            console.print("[red]Transfer failed.[/red]")
            raise typer.Exit(1)
    except MoveError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


# ── sweep ──────────────────────────────────────────────────────────────


@app.command()
def sweep(
    top: int = typer.Option(10, "--top", "-t", help="Number of top items to show."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-confirm safe targets."),
) -> None:
    """Quick one-shot: scan + offer to clean the biggest items."""
    from besen.cleaner import clean_targets
    from besen.scanner import scan_targets

    with console.status("[bold]Scanning..."):
        targets = scan_targets()

    # Filter to existing with size, sort by size
    targets = [t for t in targets if t.exists and t.size_bytes > 0]
    targets.sort(key=lambda t: t.size_bytes, reverse=True)

    if not targets:
        console.print("[green]Your Mac is already clean![/green]")
        raise typer.Exit()

    top_targets = targets[:top]
    total = sum(t.size_bytes for t in top_targets)

    console.print(
        Panel(
            f"Found [bold]{naturalsize(total, binary=True)}[/bold] "
            f"across {len(top_targets)} locations",
            title="[bold]Sweep Summary[/bold]",
        )
    )

    for i, t in enumerate(top_targets, 1):
        safe = "[green]safe[/green]" if t.safe_to_clean else "[yellow]caution[/yellow]"
        console.print(
            f"  {i:2d}. {t.name:<25s} "
            f"{naturalsize(t.size_bytes, binary=True):>10s}  "
            f"({t.category.value})  {safe}"
        )

    console.print()

    if yes:
        # Only auto-clean safe targets
        safe_targets = [t for t in top_targets if t.safe_to_clean]
        if safe_targets:
            console.print(
                f"[bold]Auto-cleaning {len(safe_targets)} safe targets...[/bold]"
            )
            freed = clean_targets(safe_targets, source="sweep")
            console.print(
                f"\n[bold green]Swept![/bold green] Freed "
                f"[bold]{naturalsize(freed, binary=True)}[/bold]"
            )
        else:
            console.print("[yellow]No safe targets to auto-clean.[/yellow]")
    else:
        if typer.confirm("Clean all safe targets?", default=False):
            safe_targets = [t for t in top_targets if t.safe_to_clean]
            freed = clean_targets(safe_targets, source="sweep")
            console.print(
                f"\n[bold green]Swept![/bold green] Freed "
                f"[bold]{naturalsize(freed, binary=True)}[/bold]"
            )
        else:
            console.print("[dim]Run 'besen clean' for per-category control.[/dim]")


# ── cpu ───────────────────────────────────────────────────────────────


@app.command()
def cpu(
    top: int = typer.Option(15, "--top", "-t", help="Number of top processes to show."),
    memory: bool = typer.Option(False, "--memory", "-m", help="Also show top memory consumers."),
    stale_hours: float = typer.Option(24, "--stale", help="Flag processes idle longer than N hours."),
    kill: bool = typer.Option(False, "--kill", "-k", help="Offer to kill stale/zombie processes."),
    zombie: bool = typer.Option(False, "--zombie", "-z", help="Kill zombie processes immediately (with --kill)."),
) -> None:
    """Show CPU usage, top processes, zombies, and stale processes."""
    import psutil
    from rich.columns import Columns

    from besen.procs import (
        find_stale,
        find_zombies,
        get_all_procs,
        get_system_snapshot,
        top_cpu,
        top_memory,
    )

    # ── System overview ──
    with console.status("[bold]Sampling CPU (1s)..."):
        snap = get_system_snapshot()

    # CPU bar
    cpu_pct = snap.cpu_percent
    bar_len = 30
    bar_filled = int(cpu_pct / 100 * bar_len)
    if cpu_pct > 80:
        color = "red"
    elif cpu_pct > 50:
        color = "yellow"
    else:
        color = "green"
    bar = f"[{color}]{'█' * bar_filled}[/{color}]{'░' * (bar_len - bar_filled)}"

    # Memory bar
    mem_pct = snap.memory_percent
    mem_filled = int(mem_pct / 100 * bar_len)
    if mem_pct > 85:
        mcolor = "red"
    elif mem_pct > 65:
        mcolor = "yellow"
    else:
        mcolor = "green"
    mem_bar = f"[{mcolor}]{'█' * mem_filled}[/{mcolor}]{'░' * (bar_len - mem_filled)}"

    # Load average color
    cores = snap.cpu_count_physical or 1
    load_color = "green"
    if snap.load_avg_1 > cores * 2:
        load_color = "red"
    elif snap.load_avg_1 > cores:
        load_color = "yellow"

    sys_panel = (
        f"  CPU   {bar}  {cpu_pct:.1f}%  "
        f"({snap.cpu_count_physical}P/{snap.cpu_count_logical}L cores)\n"
        f"  Mem   {mem_bar}  {mem_pct:.1f}%  "
        f"({snap.memory_used_mb:.0f} / {snap.memory_total_mb:.0f} MB)\n"
        f"  Swap  {snap.swap_used_mb:.0f} / {snap.swap_total_mb:.0f} MB "
        f"({snap.swap_percent:.0f}%)\n"
        f"  Load  [{load_color}]{snap.load_avg_1:.2f}[/{load_color}]  "
        f"{snap.load_avg_5:.2f}  {snap.load_avg_15:.2f}  "
        f"(1m / 5m / 15m)"
    )
    console.print(Panel(sys_panel, title="[bold]System Overview[/bold]"))

    # Per-core sparkline
    core_strs = []
    for i, pct in enumerate(snap.cpu_per_core):
        if pct > 80:
            c = "red"
        elif pct > 50:
            c = "yellow"
        else:
            c = "green"
        core_strs.append(f"[{c}]{pct:5.1f}%[/{c}]")
    console.print(Panel(
        "  ".join(core_strs),
        title=f"[bold]Per-Core Usage ({len(snap.cpu_per_core)} cores)[/bold]",
    ))

    # ── Process sampling ──
    with console.status("[bold]Sampling processes (1s)..."):
        procs = get_all_procs()

    # ── Top CPU ──
    cpu_procs = top_cpu(procs, top)
    table = Table(title=f"Top {top} CPU Consumers")
    table.add_column("PID", style="dim", justify="right", width=7)
    table.add_column("Name", style="bold", max_width=22)
    table.add_column("CPU%", justify="right", width=6)
    table.add_column("Mem MB", justify="right", width=8)
    table.add_column("Threads", justify="right", width=7)
    table.add_column("Uptime", justify="right", width=8)
    table.add_column("User", style="dim", max_width=12)
    table.add_column("Command", style="dim", max_width=40, no_wrap=True)

    for p in cpu_procs:
        cpu_style = ""
        if p.cpu_percent > 100:
            cpu_style = "bold red"
        elif p.cpu_percent > 50:
            cpu_style = "yellow"
        table.add_row(
            str(p.pid),
            p.name,
            f"[{cpu_style}]{p.cpu_percent:.1f}[/{cpu_style}]" if cpu_style else f"{p.cpu_percent:.1f}",
            f"{p.memory_mb:.0f}",
            str(p.num_threads),
            p.uptime_human,
            p.username,
            p.cmdline[:40],
        )
    console.print(table)

    # ── Top Memory (optional) ──
    if memory:
        mem_procs = top_memory(procs, top)
        mtable = Table(title=f"Top {top} Memory Consumers")
        mtable.add_column("PID", style="dim", justify="right", width=7)
        mtable.add_column("Name", style="bold", max_width=22)
        mtable.add_column("Mem MB", justify="right", width=8)
        mtable.add_column("CPU%", justify="right", width=6)
        mtable.add_column("Uptime", justify="right", width=8)
        mtable.add_column("Command", style="dim", max_width=50, no_wrap=True)

        for p in mem_procs:
            mem_style = ""
            if p.memory_mb > 1024:
                mem_style = "bold red"
            elif p.memory_mb > 512:
                mem_style = "yellow"
            mtable.add_row(
                str(p.pid),
                p.name,
                f"[{mem_style}]{p.memory_mb:.0f}[/{mem_style}]" if mem_style else f"{p.memory_mb:.0f}",
                f"{p.cpu_percent:.1f}",
                p.uptime_human,
                p.cmdline[:50],
            )
        console.print(mtable)

    # ── Zombies ──
    zombies = find_zombies(procs)
    if zombies:
        console.print(f"\n[bold red]Zombie Processes ({len(zombies)}):[/bold red]")
        for z in zombies:
            console.print(
                f"  PID {z.pid}  {z.name}  "
                f"(parent likely gone, uptime {z.uptime_human})"
            )
        if kill and not settings.dry_run:
            do_kill = zombie or typer.confirm(f"\nKill {len(zombies)} zombie(s)?", default=False)
            if do_kill:
                import signal
                killed = 0
                for z in zombies:
                    try:
                        psutil.Process(z.pid).send_signal(signal.SIGKILL)
                        console.print(f"  [green]Killed[/green] PID {z.pid} ({z.name})")
                        killed += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        console.print(f"  [red]Failed[/red] PID {z.pid}: {e}")
                console.print(f"\n[bold green]Cleaned {killed}/{len(zombies)} zombies.[/bold green]")
    else:
        console.print("\n[green]No zombie processes.[/green]")

    # Short-circuit: if --zombie was passed, skip the stale section
    if zombie:
        return

    # ── Stale processes ──
    stale = find_stale(procs, min_hours=stale_hours)
    if stale:
        # Only show user-owned stale processes to keep it relevant
        import os
        current_user = os.getlogin()
        user_stale = [s for s in stale if s.username == current_user]

        if user_stale:
            console.print(
                f"\n[bold yellow]Stale Processes "
                f"(idle >{stale_hours:.0f}h, your user, {len(user_stale)} found):[/bold yellow]"
            )
            stable = Table(show_header=True, show_lines=False)
            stable.add_column("PID", style="dim", justify="right", width=7)
            stable.add_column("Name", style="bold", max_width=22)
            stable.add_column("CPU%", justify="right", width=6)
            stable.add_column("Mem MB", justify="right", width=8)
            stable.add_column("Uptime", justify="right", width=8)
            stable.add_column("Command", style="dim", max_width=50, no_wrap=True)

            for s in user_stale[:20]:
                stable.add_row(
                    str(s.pid),
                    s.name,
                    f"{s.cpu_percent:.1f}",
                    f"{s.memory_mb:.0f}",
                    s.uptime_human,
                    s.cmdline[:50],
                )
            console.print(stable)

            if kill and not settings.dry_run:
                if typer.confirm(f"\nKill {len(user_stale)} stale process(es)?", default=False):
                    import signal
                    for s in user_stale:
                        try:
                            psutil.Process(s.pid).send_signal(signal.SIGTERM)
                            console.print(f"  [green]Terminated[/green] PID {s.pid} ({s.name})")
                        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                            console.print(f"  [red]Failed[/red] PID {s.pid}: {e}")
        else:
            console.print(f"\n[green]No stale user processes (>{stale_hours:.0f}h idle).[/green]")
    else:
        console.print(f"\n[green]No stale processes (>{stale_hours:.0f}h idle).[/green]")


# ── watch (headless single run for daemon) ────────────────────────────


@app.command()
def watch(
    quiet: bool = typer.Option(True, "--quiet/--verbose", "-q/-V", help="Suppress output (for daemon use)."),
) -> None:
    """Single headless run — apply all auto-policies.

    This is what the daemon calls on schedule. It checks disk space,
    kills zombies, monitors CPU/memory, and sends notifications.
    """
    import json
    from datetime import datetime

    from besen.policies import (
        apply_cpu_policy,
        apply_disk_policy,
        apply_zombie_policy,
        load_policies,
    )

    policies = load_policies()
    timestamp = datetime.now().isoformat(timespec="seconds")

    results = {
        "timestamp": timestamp,
        "disk": apply_disk_policy(policies),
        "zombie": apply_zombie_policy(policies),
        "cpu": apply_cpu_policy(policies),
    }

    if not quiet:
        console.print(Panel(
            json.dumps(results, indent=2, default=str),
            title=f"[bold]Watch Run — {timestamp}[/bold]",
        ))
    else:
        # Minimal log output for daemon mode
        parts = []
        d = results["disk"]
        if d.get("cleaned"):
            parts.append(f"cleaned {naturalsize(d['freed_bytes'], binary=True)}")
        if d.get("notified"):
            parts.append("disk-low")
        z = results["zombie"]
        if z.get("killed"):
            parts.append(f"killed {z['killed']} zombies")
        c = results["cpu"]
        if c.get("memory_alert"):
            parts.append("mem-pressure")
        if c.get("high_cpu_procs"):
            parts.append(f"high-cpu: {', '.join(c['high_cpu_procs'][:3])}")

        summary = ", ".join(parts) if parts else "all clear"
        print(f"[{timestamp}] {summary}")


# ── daemon ────────────────────────────────────────────────────────────


daemon_app = typer.Typer(
    name="daemon",
    help="Background scheduler management.",
    no_args_is_help=True,
)
app.add_typer(daemon_app, name="daemon")


@daemon_app.command()
def install(
    interval: int = typer.Option(60, "--interval", "-i", help="Run interval in minutes."),
) -> None:
    """Install the background daemon (launchd)."""
    from besen.daemon import install as do_install
    from besen.policies import CONFIG_PATH, load_policies, save_policies

    # Ensure policies config exists with defaults
    if not CONFIG_PATH.exists():
        save_policies(load_policies())
        console.print(f"[dim]Created default policies: {CONFIG_PATH}[/dim]")

    try:
        msg = do_install(interval_minutes=interval)
        console.print(f"[bold green]Daemon installed.[/bold green]\n\n{msg}")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@daemon_app.command()
def uninstall() -> None:
    """Uninstall the background daemon."""
    from besen.daemon import uninstall as do_uninstall

    msg = do_uninstall()
    console.print(msg)


@daemon_app.command(name="status")
def daemon_status() -> None:
    """Show daemon status and recent logs."""
    from besen.daemon import read_logs
    from besen.daemon import status as get_status

    info = get_status()

    if not info["installed"]:
        console.print("[yellow]Daemon not installed.[/yellow]")
        console.print("[dim]Run: besen daemon install[/dim]")
        return

    state = "[green]running[/green]" if info["running"] else "[red]stopped[/red]"
    console.print(Panel(
        f"  Status:   {state}\n"
        f"  Interval: every {info['interval_min']} min\n"
        f"  Plist:    {info['plist_path']}\n"
        f"  Log:      {info['log_path']}",
        title="[bold]Besen Daemon[/bold]",
    ))

    # Show recent log
    logs = read_logs(10)
    if logs:
        console.print(f"\n[bold]Recent activity:[/bold]\n{logs}")


@daemon_app.command()
def logs(
    lines: int = typer.Option(30, "--lines", "-n", help="Number of log lines to show."),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output (tail -f)."),
) -> None:
    """Show daemon logs."""
    from besen.daemon import LOG_OUT, read_logs

    if follow:
        import subprocess
        if not LOG_OUT.exists():
            console.print("[yellow]No log file yet — daemon hasn't run.[/yellow]")
            raise typer.Exit()
        console.print(f"[dim]Following {LOG_OUT} (Ctrl+C to stop)...[/dim]\n")
        try:
            subprocess.run(["tail", "-f", str(LOG_OUT)])
        except KeyboardInterrupt:
            pass
    else:
        console.print(read_logs(lines))


# ── policies ──────────────────────────────────────────────────────────


@app.command()
def policies() -> None:
    """Show and edit auto-policies configuration."""
    from besen.policies import CONFIG_PATH, load_policies, save_policies

    p = load_policies()

    console.print(Panel(
        f"  [bold]Disk Policy[/bold]\n"
        f"    Enabled:          {'yes' if p.disk.enabled else 'no'}\n"
        f"    Auto-clean below: {p.disk.free_threshold_gb:.0f} GB free\n"
        f"    Notify below:     {p.disk.notify_threshold_gb:.0f} GB free\n"
        f"    Safe targets only: {'yes' if p.disk.safe_only else 'no'}\n\n"
        f"  [bold]Zombie Policy[/bold]\n"
        f"    Enabled:          {'yes' if p.zombie.enabled else 'no'}\n"
        f"    Auto-kill after:  {p.zombie.min_age_hours:.0f}h\n"
        f"    Notify:           {'yes' if p.zombie.notify else 'no'}\n\n"
        f"  [bold]CPU Policy[/bold]\n"
        f"    Enabled:          {'yes' if p.cpu.enabled else 'no'}\n"
        f"    High CPU alert:   >{p.cpu.high_cpu_threshold:.0f}% for {p.cpu.sustained_minutes}min\n"
        f"    Memory alert:     >{p.cpu.memory_threshold:.0f}%\n"
        f"    Auto-kill stale:  {f'{p.cpu.auto_kill_stale_hours:.0f}h' if p.cpu.auto_kill_stale_hours else 'disabled'}",
        title="[bold]Auto-Policies[/bold]",
    ))

    console.print(f"\n[dim]Config: {CONFIG_PATH}[/dim]")
    console.print("[dim]Edit the JSON file directly or use env vars to override.[/dim]")


# ── notify ────────────────────────────────────────────────────────────


@app.command()
def notify(
    message: str = typer.Argument("Besen is working.", help="Notification message."),
    title: str = typer.Option("Test", "--title", "-t", help="Notification title."),
) -> None:
    """Send a test macOS notification."""
    from besen.notifier import notify as send_notify

    success = send_notify(title=title, message=message)
    if success:
        console.print("[green]Notification sent.[/green]")
    else:
        console.print("[red]Failed to send notification.[/red]")


# ── report ────────────────────────────────────────────────────────────


@app.command()
def report(
    period: str = typer.Option(
        "all", "--period", "-p",
        help="Time period: today, week, month, year, all.",
    ),
    detail: bool = typer.Option(
        False, "--detail", "-d",
        help="Show per-target breakdown.",
    ),
) -> None:
    """Show cleanup history — how much data was cleaned over time."""
    from datetime import datetime, timedelta

    from besen.history import HISTORY_PATH, load_history, summarize, summarize_by_period

    # Determine time filter
    now = datetime.now()
    since = None
    period_label = "All Time"
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "Today"
    elif period == "week":
        since = now - timedelta(days=7)
        period_label = "Last 7 Days"
    elif period == "month":
        since = now - timedelta(days=30)
        period_label = "Last 30 Days"
    elif period == "year":
        since = now - timedelta(days=365)
        period_label = "Last 365 Days"

    events = load_history(since=since)

    if not events:
        console.print("[yellow]No cleanup history yet.[/yellow]")
        console.print("[dim]History is recorded when you run: besen clean, sweep, or the daemon.[/dim]")
        raise typer.Exit()

    # ── Summary panel ──
    s = summarize(events)
    console.print(Panel(
        f"  Total freed:   [bold green]{naturalsize(s['total_freed'], binary=True)}[/bold green]\n"
        f"  Clean events:  {s['event_count']}\n"
        f"  Period:        {period_label}",
        title="[bold]Cleanup Report[/bold]",
    ))

    # ── By source ──
    if s["by_source"]:
        src_table = Table(title="By Source", show_lines=False)
        src_table.add_column("Source", style="bold")
        src_table.add_column("Freed", justify="right", style="green")
        src_table.add_column("Events", justify="right", style="dim")

        for source, freed in s["by_source"].items():
            count = sum(1 for e in events if e.get("source") == source)
            src_table.add_row(source, naturalsize(freed, binary=True), str(count))
        console.print(src_table)

    # ── By category ──
    if s["by_category"]:
        cat_table = Table(title="By Category", show_lines=False)
        cat_table.add_column("Category", style="cyan")
        cat_table.add_column("Freed", justify="right", style="green")

        for cat, freed in s["by_category"].items():
            cat_table.add_row(cat, naturalsize(freed, binary=True))
        console.print(cat_table)

    # ── Per-target detail ──
    if detail and s["by_target"]:
        tgt_table = Table(title="By Target", show_lines=False)
        tgt_table.add_column("Target", style="bold")
        tgt_table.add_column("Freed", justify="right", style="green")
        tgt_table.add_column("Events", justify="right", style="dim")

        for target, freed in s["by_target"].items():
            count = sum(1 for e in events if e.get("target") == target)
            tgt_table.add_row(target, naturalsize(freed, binary=True), str(count))
        console.print(tgt_table)

    # ── Timeline ──
    periods = summarize_by_period(events)

    # Pick the right granularity based on the filter
    if period == "today":
        # No timeline for a single day
        pass
    elif period in ("week", "month"):
        if periods["daily"]:
            day_table = Table(title="Daily Breakdown", show_lines=False)
            day_table.add_column("Date", style="bold")
            day_table.add_column("Freed", justify="right", style="green")
            day_table.add_column("Events", justify="right", style="dim")
            day_table.add_column("", width=30)

            max_freed = max(d["freed"] for d in periods["daily"]) or 1
            for d in periods["daily"][:14]:
                bar_len = int(d["freed"] / max_freed * 25)
                bar = f"[green]{'█' * bar_len}[/green]{'░' * (25 - bar_len)}"
                day_table.add_row(
                    d["period"],
                    naturalsize(d["freed"], binary=True),
                    str(d["count"]),
                    bar,
                )
            console.print(day_table)
    elif period == "year":
        if periods["monthly"]:
            mon_table = Table(title="Monthly Breakdown", show_lines=False)
            mon_table.add_column("Month", style="bold")
            mon_table.add_column("Freed", justify="right", style="green")
            mon_table.add_column("Events", justify="right", style="dim")
            mon_table.add_column("", width=30)

            max_freed = max(m["freed"] for m in periods["monthly"]) or 1
            for m in periods["monthly"][:12]:
                bar_len = int(m["freed"] / max_freed * 25)
                bar = f"[green]{'█' * bar_len}[/green]{'░' * (25 - bar_len)}"
                mon_table.add_row(
                    m["period"],
                    naturalsize(m["freed"], binary=True),
                    str(m["count"]),
                    bar,
                )
            console.print(mon_table)
    else:
        # "all" — show monthly if enough data, else daily
        timeline = periods["monthly"] if len(periods["monthly"]) > 1 else periods["daily"]
        label = "Monthly" if len(periods["monthly"]) > 1 else "Daily"
        if timeline:
            tl_table = Table(title=f"{label} Breakdown", show_lines=False)
            tl_table.add_column("Period", style="bold")
            tl_table.add_column("Freed", justify="right", style="green")
            tl_table.add_column("Events", justify="right", style="dim")
            tl_table.add_column("", width=30)

            max_freed = max(t["freed"] for t in timeline) or 1
            for t in timeline[:14]:
                bar_len = int(t["freed"] / max_freed * 25)
                bar = f"[green]{'█' * bar_len}[/green]{'░' * (25 - bar_len)}"
                tl_table.add_row(
                    t["period"],
                    naturalsize(t["freed"], binary=True),
                    str(t["count"]),
                    bar,
                )
            console.print(tl_table)

    console.print(f"\n[dim]History: {HISTORY_PATH}[/dim]")
