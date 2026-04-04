#!/usr/bin/env python3
"""Check active streams on Emby and Jellyfin servers."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── Configuration ────────────────────────────────────────────────────────────
# Loaded from a .env file in the same directory as this script.
# Copy .env.example to .env and fill in your values.


def load_dotenv(env_path: Path) -> None:
    """Load key=value pairs from a .env file into os.environ."""
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


load_dotenv(Path(__file__).resolve().parent / ".env")

EMBY_URL = os.environ.get("EMBY_URL", "http://localhost:8096")
EMBY_API_KEY = os.environ.get("EMBY_API_KEY", "")
JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://localhost:8097")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "")

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


# ── Emby ─────────────────────────────────────────────────────────────────────

def check_emby() -> list[dict]:
    """Return list of active Emby streams."""
    url = f"{EMBY_URL}/emby/Sessions?api_key={EMBY_API_KEY}"
    try:
        sessions = api_get(url)
    except (URLError, OSError) as e:
        print(f"  {C.RED}✗ Could not reach Emby: {e}{C.RESET}")
        return []

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


# ── Jellyfin ─────────────────────────────────────────────────────────────────

def check_jellyfin() -> list[dict]:
    """Return list of active Jellyfin streams."""
    url = f"{JELLYFIN_URL}/Sessions"
    headers = {"X-Emby-Token": JELLYFIN_API_KEY}
    try:
        sessions = api_get(url, headers=headers)
    except (URLError, OSError) as e:
        print(f"  {C.RED}✗ Could not reach Jellyfin: {e}{C.RESET}")
        return []

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


# ── Output ───────────────────────────────────────────────────────────────────

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
    print(f"{C.BOLD}{C.WHITE}═══ Stream Check — {timestamp} ═══{C.RESET}\n")

    if not EMBY_API_KEY and not JELLYFIN_API_KEY:
        print(f"{C.RED}No API keys configured. Copy .env.example to .env and add your keys.{C.RESET}")
        sys.exit(1)

    emby_streams = []
    jf_streams = []

    if EMBY_API_KEY:
        print(f"{C.BOLD}{C.GREEN}┌─ Emby ─────────────────────────────{C.RESET}")
        emby_streams = check_emby()
        print_streams("Emby", emby_streams)
    else:
        print(f"{C.DIM}┌─ Emby ──────────────── (skipped, no API key){C.RESET}")
        print()

    if JELLYFIN_API_KEY:
        print(f"{C.BOLD}{C.BLUE}┌─ Jellyfin ─────────────────────────{C.RESET}")
        jf_streams = check_jellyfin()
        print_streams("Jellyfin", jf_streams)
    else:
        print(f"{C.DIM}┌─ Jellyfin ──────────── (skipped, no API key){C.RESET}")
        print()

    total = len(emby_streams) + len(jf_streams)
    color = C.GREEN if total == 0 else C.CYAN
    print(f"{C.BOLD}── Total active streams: {color}{total}{C.RESET}")


if __name__ == "__main__":
    main()