# Besen

**A CLI broom for your Mac.** Scan, clean, and monitor — without the bloat.

<p align="center">
  <code>besen</code> — German for "broom"
</p>

---

## Why Besen?

CleanMyMac costs money. It runs a heavy Electron UI. It phones home. It does things you could do yourself in a terminal — if someone wrapped it properly.

So we built Besen: a single Python CLI that replaces the core of what CleanMyMac does, plus things it doesn't — like CPU monitoring, zombie process detection, and moving files to your NAS in one command. No GUI. No subscription. No telemetry. Just a fast, honest tool that shows you where your disk space went and helps you get it back.

**What 60 GB of hidden caches looks like when you finally find them:**

```
besen scan --sort category
```

```
                              Cleanable Locations
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┳━━━━━━┓
┃ #   ┃ Name                  ┃ Category         ┃       Size ┃ Items ┃ Safe ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━╇━━━━━━┩
│ 1   │ uv Cache              │ Dotfolder Cache  │   17.8 GiB │  1.4M │ yes  │
│ 2   │ OpenCode Data         │ IDE Cache        │    5.9 GiB │  280K │  !   │
│ 3   │ Node.js Versions (nvm)│ Runtime Versions │    4.4 GiB │  307K │  !   │
│ 4   │ Continue.dev          │ IDE Cache        │    4.0 GiB │   11K │  !   │
│ 5   │ Tabby                 │ IDE Cache        │    2.9 GiB │   682 │  !   │
│ ...                                                                         │
│     │                       │                  │            │       │      │
│     │ Total reclaimable:    │                  │   62.4 GiB │       │      │
└─────┴───────────────────────┴──────────────────┴────────────┴───────┴──────┘
```

---

## What It Does

| Command | Purpose |
|---------|---------|
| `besen scan` | Scan **44 known locations** — caches, dotfolders, IDE data, AI models, runtime versions, Docker, Xcode, package managers, logs, trash |
| `besen space` | Filesystem overview with usage bars and NAS mount status |
| `besen big` | Find large files and directories anywhere on disk |
| `besen clean` | Interactive cleanup — pick items by number, range, or category |
| `besen move` | Move files to NAS via rsync with verification |
| `besen sweep` | Quick one-shot: scan + offer to clean the biggest safe items |
| `besen cpu` | System health: CPU/memory overview, top processes, zombie detection, stale process finder |

---

## Install

```bash
# Clone
git clone https://github.com/48Nauts-Operator/besen.git
cd besen

# Install (editable mode — changes take effect immediately)
pip install -e .

# Verify
besen --version
```

**Requirements:** Python 3.11+, macOS. Dependencies are minimal and install automatically:
- `typer` — CLI framework
- `rich` — terminal formatting
- `psutil` — system monitoring
- `pydantic-settings` — configuration
- `humanize` — human-readable sizes

---

## Usage

### Scan everything

```bash
besen scan                    # All 44 locations, sorted by size
besen scan --category docker  # Only Docker-related items
besen scan --category ide     # Only IDE caches
besen scan --sort category    # Group by category
besen scan --all              # Include locations that don't exist
```

### Check disk space

```bash
besen space
```

```
╭──────────────── Macintosh HD (/) ─────────────────╮
│  ██████████████████████░░░░░░░░  73.2%            │
│                                                    │
│  Total:  926.4 GiB                                │
│  Used:   678.1 GiB                                │
│  Free:   248.3 GiB                                │
╰────────────────────────────────────────────────────╯

● NAS mounted at /Volumes/Tron
```

### Find space hogs

```bash
besen big                           # Large items in home (>500 MB)
besen big / --threshold 1000        # Full disk, >1 GB
besen big ~/Projects --limit 10     # Top 10 in Projects
```

### Clean up

```bash
besen clean                  # Interactive: shows table, pick by number
besen clean -p 1,3,5-7      # Clean specific items
besen clean -p all           # Clean everything (with confirmation)
besen clean -y               # Auto-clean all safe items
besen clean -c cache         # Only caches
besen clean --dry-run        # Preview without deleting
```

### Move to NAS

```bash
besen move ~/old-project              # Move to /Volumes/Tron
besen move ~/dataset -d archive/2024  # Move to specific NAS subdirectory
besen move ~/big-file --delete        # Delete source after verified transfer
```

### Monitor system health

```bash
besen cpu                    # Full overview: CPU, memory, top procs, zombies
besen cpu --top 5 --memory   # Compact view with memory table
besen cpu --kill --zombie    # Kill zombie processes immediately
besen cpu --kill             # Offer to kill zombies and stale processes
besen cpu --stale 48         # Flag processes idle for >48 hours
```

---

## What It Scans

Besen knows about **44 locations** across 14 categories:

| Category | What it finds |
|----------|---------------|
| **System Cache** | `~/Library/Caches`, Saved Application State |
| **App Cache** | Safari, Chrome, Firefox, Spotify, Slack |
| **Package Manager** | Homebrew, pip, npm, yarn, pnpm, Cargo, Go modules |
| **Dev Tools** | CocoaPods, Gradle, Maven |
| **Docker** | Docker Desktop data, Podman containers |
| **Xcode** | DerivedData, Archives, iOS DeviceSupport |
| **Logs** | System logs, user logs, crash reports |
| **Dotfolder Cache** | `.cache/uv`, `.bun`, `.expo`, `.amplify`, Atom (dead editor), old backups |
| **IDE Cache** | VS Code, Cursor, Windsurf, Continue.dev, Tabby, OpenCode, Codeium, Codex |
| **AI Models** | LM Studio, Ollama, EasyOCR, Sherpa, Whisper |
| **Runtime Versions** | nvm (Node.js), pyenv (Python), rustup (Rust) |
| **Trash** | `~/.Trash` |
| **Downloads** | `~/Downloads` |
| **Misc** | Solana tools, sparse bundles |

Each location has a **safety level**:
- **yes** — Pure cache, auto-regenerated. Safe to delete anytime.
- **!** — Review before deleting. May contain data you care about or affect running services.

---

## Configuration

All settings can be overridden via environment variables with the `BESEN_` prefix:

```bash
export BESEN_NAS_PATH=/Volumes/MyNAS       # Default: /Volumes/Tron
export BESEN_BIG_THRESHOLD_MB=200          # Default: 500
export BESEN_DRY_RUN=true                  # Preview all operations
```

Protected directories (never touched by clean):
- `~/Documents`, `~/Desktop`
- `~/.ssh`, `~/.gnupg`, `~/.claude`

---

## Philosophy

1. **No GUI needed.** If you're comfortable in a terminal, you don't need a $35/year app with animations to delete your caches.

2. **Show, don't assume.** Besen never deletes without showing you exactly what and how much. Every destructive action requires confirmation.

3. **Safe by default.** Items are marked safe or caution. Auto-clean (`-y`) only touches safe items. The `--dry-run` flag previews everything.

4. **Fast and honest.** Uses `os.scandir` for speed, subprocess with timeouts for large dirs, and `psutil` for system stats. No background processes, no telemetry, no phoning home.

5. **One tool, not ten.** Replaces the scattered workflow of `ncdu` + `docker system prune` + `brew cleanup` + Activity Monitor + manual `du -sh` archaeology into a single CLI.

---

## Roadmap

### Daemon Mode (next)
- Background scheduler via `launchd` plist or cron
- Configurable intervals (hourly, daily, weekly)
- Auto-clean safe targets on schedule
- Disk pressure detection — trigger cleanup when free space drops below threshold

### Notifications
- macOS native notifications via `osascript` / `terminal-notifier`
- Alerts for: disk space low, CPU sustained high, memory pressure, new zombie processes
- Configurable thresholds and cooldown periods

### Auto-Kill Policies
- Define rules for automatic zombie cleanup
- Stale process policies (e.g., kill Node processes idle >48h)
- Watchdog for runaway processes (CPU >200% for >10 minutes)

### Reporting
- Weekly summary: space cleaned, zombies killed, top consumers
- Trend tracking: disk usage over time
- Export to JSON for dashboarding

---

## Project Structure

```
besen/
├── __init__.py     # Package version
├── cli.py          # Typer CLI with 7 commands
├── config.py       # pydantic-settings (BESEN_ env prefix)
├── scanner.py      # 44 scan targets + disk usage + large file finder
├── cleaner.py      # Safe cleanup with confirmation
├── mover.py        # NAS move via rsync with verification
└── procs.py        # CPU/memory monitoring, zombie/stale detection
```

---

## License

MIT

---

<p align="center">
  Built because CleanMyMac shouldn't cost money for what a broom can do.
</p>
