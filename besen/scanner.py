"""Scanner — discovers cleanable locations on macOS and measures their size."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from besen.config import HOME, settings


class Category(str, Enum):
    """Cleanup categories."""

    SYSTEM_CACHE = "System Cache"
    APP_CACHE = "App Cache"
    PACKAGE_MANAGER = "Package Manager"
    DEV_TOOLS = "Dev Tools"
    DOCKER = "Docker"
    XCODE = "Xcode"
    LOGS = "Logs"
    TRASH = "Trash"
    DOWNLOADS = "Downloads"
    DOTFOLDER = "Dotfolder Cache"
    AI_MODELS = "AI Models"
    RUNTIME_VERSIONS = "Runtime Versions"
    IDE_CACHE = "IDE Cache"
    MISC = "Misc"


@dataclass
class CleanTarget:
    """A single cleanable location."""

    name: str
    path: Path
    category: Category
    description: str
    size_bytes: int = 0
    exists: bool = False
    item_count: int = 0
    safe_to_clean: bool = True  # False means warn before cleaning


# ── Known cleanable locations on macOS ─────────────────────────────────

TARGETS: list[dict] = [
    # ── System Caches ──
    {
        "name": "User Cache",
        "path": HOME / "Library/Caches",
        "category": Category.SYSTEM_CACHE,
        "description": "Per-app caches (regenerated on demand)",
    },
    {
        "name": "System Logs",
        "path": Path("/private/var/log"),
        "category": Category.LOGS,
        "description": "System log files",
    },
    {
        "name": "User Logs",
        "path": HOME / "Library/Logs",
        "category": Category.LOGS,
        "description": "Application log files",
    },
    {
        "name": "Crash Reports",
        "path": HOME / "Library/Logs/DiagnosticReports",
        "category": Category.LOGS,
        "description": "App crash reports",
    },
    {
        "name": "Saved App State",
        "path": HOME / "Library/Saved Application State",
        "category": Category.SYSTEM_CACHE,
        "description": "Window positions and state",
    },
    # ── App Caches ──
    {
        "name": "Safari Cache",
        "path": HOME / "Library/Caches/com.apple.Safari",
        "category": Category.APP_CACHE,
        "description": "Safari browser cache",
    },
    {
        "name": "Chrome Cache",
        "path": HOME / "Library/Caches/Google/Chrome",
        "category": Category.APP_CACHE,
        "description": "Chrome browser cache",
    },
    {
        "name": "Firefox Cache",
        "path": HOME / "Library/Caches/Firefox",
        "category": Category.APP_CACHE,
        "description": "Firefox browser cache",
    },
    {
        "name": "Spotify Cache",
        "path": HOME / "Library/Caches/com.spotify.client",
        "category": Category.APP_CACHE,
        "description": "Spotify offline cache",
    },
    {
        "name": "Slack Cache",
        "path": HOME / "Library/Application Support/Slack/Cache",
        "category": Category.APP_CACHE,
        "description": "Slack app cache",
    },
    # ── Package Managers ──
    {
        "name": "Homebrew Cache",
        "path": HOME / "Library/Caches/Homebrew",
        "category": Category.PACKAGE_MANAGER,
        "description": "Downloaded bottles and source tarballs",
    },
    {
        "name": "pip Cache",
        "path": HOME / "Library/Caches/pip",
        "category": Category.PACKAGE_MANAGER,
        "description": "Python pip download cache",
    },
    {
        "name": "npm Cache",
        "path": HOME / ".npm/_cacache",
        "category": Category.PACKAGE_MANAGER,
        "description": "Node.js npm cache",
    },
    {
        "name": "yarn Cache",
        "path": HOME / "Library/Caches/Yarn",
        "category": Category.PACKAGE_MANAGER,
        "description": "Yarn package cache",
    },
    {
        "name": "pnpm Store",
        "path": HOME / "Library/pnpm/store",
        "category": Category.PACKAGE_MANAGER,
        "description": "pnpm content-addressable store",
        "safe_to_clean": False,
    },
    {
        "name": "Cargo Registry",
        "path": HOME / ".cargo/registry",
        "category": Category.PACKAGE_MANAGER,
        "description": "Rust crate registry cache",
    },
    {
        "name": "Go Module Cache",
        "path": HOME / "go/pkg/mod/cache",
        "category": Category.PACKAGE_MANAGER,
        "description": "Go module download cache",
    },
    # ── Dev Tools ──
    {
        "name": "CocoaPods Cache",
        "path": HOME / "Library/Caches/CocoaPods",
        "category": Category.DEV_TOOLS,
        "description": "iOS dependency cache",
    },
    {
        "name": "Gradle Cache",
        "path": HOME / ".gradle/caches",
        "category": Category.DEV_TOOLS,
        "description": "Gradle build cache",
    },
    {
        "name": "Maven Repository",
        "path": HOME / ".m2/repository",
        "category": Category.DEV_TOOLS,
        "description": "Local Maven artifact cache",
        "safe_to_clean": False,
    },
    # ── Docker ──
    {
        "name": "Docker Data",
        "path": HOME / "Library/Containers/com.docker.docker/Data",
        "category": Category.DOCKER,
        "description": "Docker Desktop data (images, volumes, build cache)",
        "safe_to_clean": False,
    },
    # ── Xcode ──
    {
        "name": "Xcode DerivedData",
        "path": HOME / "Library/Developer/Xcode/DerivedData",
        "category": Category.XCODE,
        "description": "Build products and indexes",
    },
    {
        "name": "Xcode Archives",
        "path": HOME / "Library/Developer/Xcode/Archives",
        "category": Category.XCODE,
        "description": "Old Xcode build archives",
    },
    {
        "name": "iOS DeviceSupport",
        "path": HOME / "Library/Developer/Xcode/iOS DeviceSupport",
        "category": Category.XCODE,
        "description": "Debug symbols for connected devices",
    },
    # ── User dirs ──
    {
        "name": "Trash",
        "path": HOME / ".Trash",
        "category": Category.TRASH,
        "description": "Files in the Trash",
    },
    {
        "name": "Downloads",
        "path": HOME / "Downloads",
        "category": Category.DOWNLOADS,
        "description": "Downloaded files",
        "safe_to_clean": False,
    },
    # ── Dotfolder Caches (XDG / tool caches in ~/) ──
    {
        "name": "uv Cache",
        "path": HOME / ".cache/uv",
        "category": Category.DOTFOLDER,
        "description": "Python uv package cache (clean with 'uv cache clean')",
    },
    {
        "name": "Whisper Cache",
        "path": HOME / ".cache/whisper",
        "category": Category.DOTFOLDER,
        "description": "Whisper model cache (re-downloads on demand)",
    },
    {
        "name": "yt-dlp Cache",
        "path": HOME / ".cache/yt-dlp",
        "category": Category.DOTFOLDER,
        "description": "yt-dlp download cache",
    },
    {
        "name": "Bun Cache",
        "path": HOME / ".bun/install/cache",
        "category": Category.DOTFOLDER,
        "description": "Bun package install cache",
    },
    {
        "name": "Expo Cache",
        "path": HOME / ".expo",
        "category": Category.DOTFOLDER,
        "description": "Expo CLI cache and project templates",
    },
    {
        "name": "Amplify Cache",
        "path": HOME / ".amplify",
        "category": Category.DOTFOLDER,
        "description": "AWS Amplify CLI cache",
    },
    {
        "name": "pipx Installs",
        "path": HOME / ".local/pipx",
        "category": Category.DOTFOLDER,
        "description": "pipx-installed Python tools (review with 'pipx list')",
        "safe_to_clean": False,
    },
    {
        "name": "Browseruse Cache",
        "path": HOME / ".config/browseruse",
        "category": Category.DOTFOLDER,
        "description": "Browser automation cache/data",
    },
    {
        "name": "Old Claude Backup",
        "path": HOME / ".claude-backup_2025-09-08",
        "category": Category.DOTFOLDER,
        "description": "Old Claude Code config backup (Sep 2025)",
    },
    {
        "name": "Atom Editor (dead)",
        "path": HOME / ".atom",
        "category": Category.DOTFOLDER,
        "description": "Atom editor (sunsetted Dec 2022) — safe to remove entirely",
    },
    {
        "name": "Sparse Bundle",
        "path": HOME / ".workspace.sparsebundle",
        "category": Category.DOTFOLDER,
        "description": "macOS encrypted disk image — check if still needed",
        "safe_to_clean": False,
    },
    # ── IDE Caches ──
    {
        "name": "VS Code Extensions",
        "path": HOME / ".vscode",
        "category": Category.IDE_CACHE,
        "description": "VS Code extensions and user data",
        "safe_to_clean": False,
    },
    {
        "name": "VS Code Server",
        "path": HOME / ".vscode-server",
        "category": Category.IDE_CACHE,
        "description": "VS Code remote server cache (auto-reinstalls)",
    },
    {
        "name": "Cursor IDE",
        "path": HOME / ".cursor",
        "category": Category.IDE_CACHE,
        "description": "Cursor IDE data and extensions",
        "safe_to_clean": False,
    },
    {
        "name": "Cursor Server",
        "path": HOME / ".cursor-server",
        "category": Category.IDE_CACHE,
        "description": "Cursor remote server cache (auto-reinstalls)",
    },
    {
        "name": "Windsurf IDE",
        "path": HOME / ".windsurf",
        "category": Category.IDE_CACHE,
        "description": "Windsurf IDE data — remove if no longer using",
        "safe_to_clean": False,
    },
    {
        "name": "Continue.dev",
        "path": HOME / ".continue",
        "category": Category.IDE_CACHE,
        "description": "Continue AI assistant data — remove if no longer using",
        "safe_to_clean": False,
    },
    {
        "name": "Codeium",
        "path": HOME / ".codeium",
        "category": Category.IDE_CACHE,
        "description": "Codeium AI code completion data",
    },
    {
        "name": "Codex CLI",
        "path": HOME / ".codex",
        "category": Category.IDE_CACHE,
        "description": "OpenAI Codex CLI cache",
    },
    {
        "name": "Tabby",
        "path": HOME / ".tabby",
        "category": Category.IDE_CACHE,
        "description": "Tabby terminal data/models",
        "safe_to_clean": False,
    },
    {
        "name": "OpenCode Data",
        "path": HOME / ".local/share/opencode",
        "category": Category.IDE_CACHE,
        "description": "OpenCode session data — remove if no longer using",
        "safe_to_clean": False,
    },
    # ── AI Model Directories ──
    {
        "name": "LM Studio Models",
        "path": HOME / ".lmstudio",
        "category": Category.AI_MODELS,
        "description": "Local LLM models (~110 GB) — audit unused models",
        "safe_to_clean": False,
    },
    {
        "name": "Ollama Models",
        "path": HOME / ".ollama",
        "category": Category.AI_MODELS,
        "description": "Ollama model files (list with 'ollama list')",
        "safe_to_clean": False,
    },
    {
        "name": "EasyOCR Models",
        "path": HOME / ".EasyOCR",
        "category": Category.AI_MODELS,
        "description": "EasyOCR text recognition models",
    },
    {
        "name": "Sherpa Models",
        "path": HOME / ".sherpa-models",
        "category": Category.AI_MODELS,
        "description": "Sherpa speech/NLP models",
        "safe_to_clean": False,
    },
    {
        "name": "Sherpa Venv",
        "path": HOME / ".sherpa-venv",
        "category": Category.AI_MODELS,
        "description": "Sherpa virtual environment",
        "safe_to_clean": False,
    },
    # ── Runtime Version Managers ──
    {
        "name": "Node.js Versions (nvm)",
        "path": HOME / ".nvm/versions",
        "category": Category.RUNTIME_VERSIONS,
        "description": "11 versions installed — only v22 active. Prune old ones",
        "safe_to_clean": False,
    },
    {
        "name": "Python Versions (pyenv)",
        "path": HOME / ".pyenv/versions",
        "category": Category.RUNTIME_VERSIONS,
        "description": "3 versions (3.9, 3.11, 3.12) — review which are needed",
        "safe_to_clean": False,
    },
    {
        "name": "Rust Toolchains",
        "path": HOME / ".rustup",
        "category": Category.RUNTIME_VERSIONS,
        "description": "Rust toolchains — prune with 'rustup toolchain list'",
        "safe_to_clean": False,
    },
    # ── Container / Cloud Data ──
    {
        "name": "Podman Containers",
        "path": HOME / ".local/share/containers",
        "category": Category.DOCKER,
        "description": "Podman container images and data",
        "safe_to_clean": False,
    },
    {
        "name": "Solana Tools",
        "path": HOME / ".local/share/solana",
        "category": Category.MISC,
        "description": "Solana validator/dev tools — remove if not developing",
        "safe_to_clean": False,
    },
]


def _dir_size(path: Path) -> tuple[int, int]:
    """Return (total_bytes, item_count) for a directory.

    Uses os.scandir for speed. Silently skips permission errors.
    """
    total = 0
    count = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                        count += 1
                    elif entry.is_dir(follow_symlinks=False):
                        sub_total, sub_count = _dir_size(Path(entry.path))
                        total += sub_total
                        count += sub_count
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError):
        pass
    return total, count


def scan_targets() -> list[CleanTarget]:
    """Scan all known targets and return them with sizes."""
    results: list[CleanTarget] = []
    for t in TARGETS:
        path = t["path"]
        target = CleanTarget(
            name=t["name"],
            path=path,
            category=t["category"],
            description=t["description"],
            safe_to_clean=t.get("safe_to_clean", True),
        )
        if path.exists():
            target.exists = True
            target.size_bytes, target.item_count = _dir_size(path)
        results.append(target)
    return results


def scan_large_files(
    root: Path = HOME,
    threshold_mb: int | None = None,
    max_results: int = 30,
) -> list[tuple[Path, int]]:
    """Find large files/dirs under `root` exceeding the threshold.

    Uses a targeted scan of top-level subdirectories to avoid spending
    minutes traversing huge trees like Docker data.
    Returns list of (path, size_bytes) sorted descending.
    """
    threshold = (threshold_mb or settings.big_threshold_mb) * 1024 * 1024
    large: list[tuple[Path, int]] = []

    # Scan each top-level subdir independently with a per-dir timeout.
    # This avoids hanging on massive dirs like Docker containers.
    try:
        children = sorted(root.iterdir())
    except (PermissionError, OSError):
        return []

    for child in children:
        if not child.is_dir():
            # Single file — check directly
            try:
                size = child.stat(follow_symlinks=False).st_size
                if size >= threshold:
                    large.append((child, size))
            except OSError:
                pass
            continue

        # Skip protected dirs
        try:
            rel = child.relative_to(HOME)
            if any(str(rel).startswith(d) for d in settings.protected_dirs):
                continue
        except ValueError:
            pass

        # Run du per subdirectory with a short timeout
        try:
            result = subprocess.run(
                ["du", "-d", "2", "-k", str(child)],
                capture_output=True,
                text=True,
                timeout=10,  # 10s per subdir — skip if too slow
            )
            for line in result.stdout.splitlines():
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                try:
                    size_kb = int(parts[0])
                except ValueError:
                    continue
                size_bytes = size_kb * 1024
                if size_bytes >= threshold:
                    large.append((Path(parts[1]), size_bytes))
        except subprocess.TimeoutExpired:
            # Dir is huge — report it at top level using _dir_size estimate
            # or just mark it as "too large to scan quickly"
            large.append((child, threshold))  # placeholder
        except (FileNotFoundError, OSError):
            pass

    # Deduplicate: keep leaf entries (remove parents if child is listed)
    large.sort(key=lambda x: str(x[0]))
    deduped: list[tuple[Path, int]] = []
    for p, size in large:
        # Skip if this is a parent of the next entry (child has more detail)
        if deduped and str(p).startswith(str(deduped[-1][0]) + "/"):
            # Replace parent with child if child is bigger or equal
            continue
        deduped.append((p, size))

    deduped.sort(key=lambda x: x[1], reverse=True)
    return deduped[:max_results]


def get_disk_usage() -> dict:
    """Get disk usage info for the boot volume and NAS."""
    import psutil

    info: dict = {"volumes": []}

    # Boot volume
    boot = psutil.disk_usage("/")
    info["volumes"].append(
        {
            "name": "Macintosh HD",
            "mount": "/",
            "total": boot.total,
            "used": boot.used,
            "free": boot.free,
            "percent": boot.percent,
        }
    )

    # NAS
    nas = settings.nas_path
    info["nas_mounted"] = nas.exists() and nas.is_mount()
    if info["nas_mounted"]:
        try:
            nas_usage = psutil.disk_usage(str(nas))
            info["volumes"].append(
                {
                    "name": "Tron (NAS)",
                    "mount": str(nas),
                    "total": nas_usage.total,
                    "used": nas_usage.used,
                    "free": nas_usage.free,
                    "percent": nas_usage.percent,
                }
            )
        except OSError:
            info["nas_mounted"] = False

    return info
