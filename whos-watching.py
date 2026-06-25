#!/usr/bin/env python3
"""Check active streams on Emby and Jellyfin, and encoding jobs on Sonarr/Radarr."""

__version__ = "1.2.0"

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── Configuration ────────────────────────────────────────────────────────────
# Loaded from a .env file. Searched in priority order:
#   1. $XDG_CONFIG_HOME/whos-watching/.env (or ~/.config/whos-watching/.env)
#   2. ./.env (current working directory)
#   3. a .env next to this script (handy when running from a source checkout)
# Real environment variables always take precedence over .env values.
# Copy .env.example to one of those locations and fill in your values.


def load_dotenv(env_path: Path) -> None:
    """Load key=value pairs from a .env file into os.environ (existing vars win)."""
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            if key and _ == "=":
                os.environ.setdefault(key.strip(), value.strip())


def config_dotenv_paths() -> list[Path]:
    """Return candidate .env locations in priority order."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(xdg) if xdg else Path.home() / ".config"
    return [
        config_home / "whos-watching" / ".env",
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
    ]


for _env_path in config_dotenv_paths():
    load_dotenv(_env_path)

EMBY_URL = os.environ.get("EMBY_URL", "http://localhost:8096")
EMBY_API_KEY = os.environ.get("EMBY_API_KEY", "")
JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://localhost:8097")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "")

# SSH host where sonarr/radarr containers run (leave empty to skip encoding checks)
ENCODE_SSH_HOST = os.environ.get("ENCODE_SSH_HOST", "")
# Comma-separated list of container names to check for ffmpeg processes
ENCODE_CONTAINERS = os.environ.get("ENCODE_CONTAINERS", "sonarr,radarr")
# Use sudo for docker commands (set to "true" if user is not in docker group)
ENCODE_USE_SUDO = os.environ.get("ENCODE_USE_SUDO", "true").lower() in ("true", "1", "yes")

# ── Colors ───────────────────────────────────────────────────────────────────

class C:
    """ANSI color codes. Automatically disabled when output is not a terminal."""
    _enabled = sys.stdout.isatty()

    RESET   = "\033[0m"  if _enabled else ""
    BOLD    = "\033[1m"  if _enabled else ""
    DIM     = "\033[2m"  if _enabled else ""
    GREEN   = "\033[32m" if _enabled else ""
    YELLOW  = "\033[33m" if _enabled else ""
    BLUE    = "\033[34m" if _enabled else ""
    MAGENTA = "\033[35m" if _enabled else ""
    CYAN    = "\033[36m" if _enabled else ""
    RED     = "\033[31m" if _enabled else ""
    WHITE   = "\033[97m" if _enabled else ""


# ── Helpers ──────────────────────────────────────────────────────────────────

def api_get(url: str, headers: dict | None = None) -> dict | list:
    """Make a GET request and return parsed JSON."""
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def format_ticks(ticks: int | None) -> str:
    """Convert .NET ticks (used by Emby/Jellyfin) to HH:MM:SS."""
    if not ticks:
        return "??:??:??"
    total_seconds = ticks // 10_000_000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_pct(position_ticks: int | None, runtime_ticks: int | None) -> str:
    """Return a percentage-complete string."""
    if not position_ticks or not runtime_ticks or runtime_ticks == 0:
        return ""
    pct = (position_ticks / runtime_ticks) * 100
    return f" ({pct:.0f}%)"


# ── Streams (Emby / Jellyfin) ────────────────────────────────────────────────

def parse_sessions(sessions: list) -> list[dict]:
    """Extract active streams from an Emby/Jellyfin Sessions response."""
    active = []
    for s in sessions:
        now_playing = s.get("NowPlayingItem")
        if not now_playing:
            continue

        play_state = s.get("PlayState", {})
        active.append({
            "user": s.get("UserName", "Unknown"),
            "client": s.get("Client", "Unknown"),
            "device": s.get("DeviceName", "Unknown"),
            "title": now_playing.get("Name", "Unknown"),
            "series": now_playing.get("SeriesName"),
            "type": now_playing.get("Type", "Unknown"),
            "position": format_ticks(play_state.get("PositionTicks")),
            "runtime": format_ticks(now_playing.get("RunTimeTicks")),
            "pct": format_pct(
                play_state.get("PositionTicks"),
                now_playing.get("RunTimeTicks"),
            ),
            "paused": play_state.get("IsPaused", False),
        })
    return active


def check_streams(name: str, url: str, headers: dict | None = None) -> list[dict]:
    """Fetch and parse active streams from an Emby/Jellyfin server."""
    try:
        sessions = api_get(url, headers=headers)
    except (URLError, OSError) as e:
        print(f"  {C.RED}✗ Could not reach {name}: {e}{C.RESET}")
        return []
    return parse_sessions(sessions)


def configured_services() -> list[dict]:
    """Streaming services that have an API key set, in display order.

    Only services with a key appear, so the tool supports Emby and Jellyfin
    side by side and silently omits whichever one you haven't configured.
    """
    services = []
    if EMBY_API_KEY:
        services.append({
            "name": "Emby",
            "color": C.GREEN,
            "url": f"{EMBY_URL}/emby/Sessions?api_key={EMBY_API_KEY}",
            "headers": None,
        })
    if JELLYFIN_API_KEY:
        services.append({
            "name": "Jellyfin",
            "color": C.BLUE,
            "url": f"{JELLYFIN_URL}/Sessions",
            "headers": {"X-Emby-Token": JELLYFIN_API_KEY},
        })
    return services


# ── Encoding (mp4_automator / ffmpeg) ────────────────────────────────────────

def check_encoding(container: str) -> list[dict]:
    """Check for running ffmpeg processes inside a Docker container via SSH."""
    try:
        # Get full ffmpeg command lines from the container
        sudo = "sudo " if ENCODE_USE_SUDO else ""
        result = subprocess.run(
            [
                "ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                ENCODE_SSH_HOST,
                f"{sudo}docker exec {container} ps -eo pid,etimes,args 2>/dev/null"
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            print(f"  {C.RED}✗ Could not reach container '{container}' on {ENCODE_SSH_HOST}{C.RESET}")
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  {C.RED}✗ SSH to {ENCODE_SSH_HOST} failed: {e}{C.RESET}")
        return []

    encodes = []
    for line in result.stdout.strip().splitlines():
        if "ffmpeg" not in line or "ps -eo" in line:
            continue

        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue

        pid, elapsed_str, cmdline = parts
        try:
            elapsed_secs = int(elapsed_str)
        except ValueError:
            elapsed_secs = 0

        # Try to extract input filename from -i argument
        input_file = "Unknown"
        m = re.search(r'-i\s+"?([^"]+)"?', cmdline)
        if m:
            input_file = Path(m.group(1)).name
        else:
            # Fallback: grab last argument that looks like a media file
            tokens = cmdline.split()
            for token in reversed(tokens):
                if re.search(r'\.(mkv|mp4|avi|m4v|ts|wmv)$', token, re.IGNORECASE):
                    input_file = Path(token).name
                    break

        # Format elapsed time
        hours, remainder = divmod(elapsed_secs, 3600)
        minutes, seconds = divmod(remainder, 60)
        elapsed_fmt = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        encodes.append({
            "pid": pid,
            "file": input_file,
            "elapsed": elapsed_fmt,
            "container": container,
        })

    return encodes


def print_encodes(encodes: list[dict]) -> None:
    """Pretty-print active encoding jobs."""
    if not encodes:
        print(f"  {C.DIM}No active encodes.{C.RESET}")
        return

    for i, e in enumerate(encodes, 1):
        print(f"  {C.BOLD}{i}.{C.RESET} {C.YELLOW}⚙  Encoding{C.RESET}: {C.WHITE}{C.BOLD}{e['file']}{C.RESET}")
        print(f"     Container: {C.CYAN}{e['container']}{C.RESET}  PID: {e['pid']}  Elapsed: {C.MAGENTA}{e['elapsed']}{C.RESET}")
        print()


# ── Output ───────────────────────────────────────────────────────────────────

def section_header(label: str, color: str) -> None:
    """Print a box-drawing section header padded to a consistent width."""
    title = f"┌─ {label} "
    print(f"{C.BOLD}{color}{title}{'─' * max(3, 38 - len(title))}{C.RESET}")


def print_streams(service: str, streams: list[dict]) -> None:
    """Pretty-print active streams for a service."""
    if not streams:
        print(f"  {C.DIM}No active streams.{C.RESET}")
        return

    for i, s in enumerate(streams, 1):
        if s["paused"]:
            state = f"{C.YELLOW}⏸  Paused{C.RESET}"
        else:
            state = f"{C.GREEN}▶  Playing{C.RESET}"

        title = s["title"]
        if s["series"]:
            title = f"{s['series']} — {title}"

        print(f"  {C.BOLD}{i}.{C.RESET} {C.CYAN}{s['user']}{C.RESET} on {s['client']} {C.DIM}({s['device']}){C.RESET}")
        print(f"     {state}: {C.WHITE}{C.BOLD}{title}{C.RESET}")
        print(f"     Progress: {C.MAGENTA}{s['position']}{C.RESET} / {s['runtime']}{C.DIM}{s['pct']}{C.RESET}")
        print()


def main() -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{C.BOLD}{C.WHITE}═══ Media Status — {timestamp} ═══{C.RESET}\n")

    services = configured_services()
    total_streams = 0
    all_encodes = []

    if not services and not ENCODE_SSH_HOST:
        print(f"  {C.DIM}Nothing configured. Add API keys to "
              f"~/.config/whos-watching/.env (see env.example).{C.RESET}\n")

    # ── Streams ── (only services with an API key are shown)

    for svc in services:
        section_header(svc["name"], svc["color"])
        streams = check_streams(svc["name"], svc["url"], svc["headers"])
        print_streams(svc["name"], streams)
        total_streams += len(streams)

    # ── Encoding ──

    if ENCODE_SSH_HOST:
        containers = [c.strip() for c in ENCODE_CONTAINERS.split(",") if c.strip()]
        section_header(f"Encoding ({ENCODE_SSH_HOST})", C.YELLOW)
        for container in containers:
            all_encodes.extend(check_encoding(container))
        print_encodes(all_encodes)

    # ── Summary ──

    total_encodes = len(all_encodes)
    s_color = C.GREEN if total_streams == 0 else C.CYAN
    e_color = C.GREEN if total_encodes == 0 else C.YELLOW
    print(f"{C.BOLD}── Streams: {s_color}{total_streams}{C.RESET}  {C.BOLD}Encodes: {e_color}{total_encodes}{C.RESET}")


if __name__ == "__main__":
    main()