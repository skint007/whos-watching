# Who's Watching?

A command-line tool to check active streams on your [Emby](https://emby.media/) and [Jellyfin](https://jellyfin.org/) media servers.

## Features

- Queries Emby and Jellyfin sessions for active streams
- Displays user, client, device, title, progress, and play state (playing/paused)
- Supports series names for TV episodes
- Colorized terminal output (auto-disabled when piped)
- No external dependencies — uses only the Python standard library

## Requirements

- Python 3.10+

## Setup

1. Copy the example environment file and fill in your values:

   ```sh
   cp .env.example .env
   ```

2. Edit `.env` with your server URLs and API keys:

   ```
   EMBY_URL=http://localhost:8096
   EMBY_API_KEY=your_emby_api_key_here

   JELLYFIN_URL=http://localhost:8097
   JELLYFIN_API_KEY=your_jellyfin_api_key_here
   ```

   Leave an API key blank to skip that server.

## Usage

```sh
python whos-watching.py
```

Example output:

```
═══ Stream Check — 2026-04-04 20:15:00 ═══

┌─ Emby ─────────────────────────────
  1. Alice on Emby Theater (Living Room TV)
     ▶  Playing: Breaking Bad — Ozymandias
     Progress: 00:32:15 / 00:47:12 (68%)

┌─ Jellyfin ─────────────────────────
  No active streams.

── Total active streams: 1
```
