# Who's Watching?

A command-line tool to check active streams on your [Jellyfin](https://jellyfin.org/)
(and [Emby](https://emby.media/)) media servers, plus any in-progress ffmpeg encoding
jobs running inside your Sonarr/Radarr Docker containers.

## Features

- Queries Emby and Jellyfin sessions for active streams; each service is shown only when its API key is configured, so you can run either or both
- Displays user, client, device, title, progress, and play state (playing/paused)
- Shows running ffmpeg encodes inside remote Docker containers over SSH (Sonarr/Radarr)
- Supports series names for TV episodes
- Colorized terminal output (auto-disabled when piped)
- No external Python dependencies — uses only the standard library

## Requirements

- Python 3.10+
- `openssh` and SSH access to the encoding host — only if you use encoding-job monitoring

## Installation

### Via [paw](https://github.com/skint007/paw) (recommended)

```sh
paw whos-watching
```

This installs the `whos-watching` command system-wide.

### From source

```sh
git clone https://github.com/skint007/whos-watching.git
cd whos-watching
python whos-watching.py
```

## Configuration

Configuration is read from a `.env` file, searched in this order (real environment
variables always take precedence):

1. `~/.config/whos-watching/.env` (or `$XDG_CONFIG_HOME/whos-watching/.env`)
2. `./.env` in the current working directory
3. a `.env` next to the script (handy when running from a checkout)

For an installed package, put your config in `~/.config/whos-watching/.env`:

```sh
mkdir -p ~/.config/whos-watching
cp /usr/share/doc/whos-watching/env.example ~/.config/whos-watching/.env
$EDITOR ~/.config/whos-watching/.env
```

Available settings:

```
# Set the API key for each server you run; unset services are hidden.
EMBY_URL=http://localhost:8096
EMBY_API_KEY=

JELLYFIN_URL=http://localhost:8097
JELLYFIN_API_KEY=your_jellyfin_api_key_here

# Encoding-job monitoring (leave ENCODE_SSH_HOST empty to skip)
ENCODE_SSH_HOST=
ENCODE_CONTAINERS=sonarr,radarr
ENCODE_USE_SUDO=false
```

Each section appears only when configured: a server shows up only if its API key is
set, and encoding checks run only if `ENCODE_SSH_HOST` is set.

## Usage

```sh
whos-watching          # if installed via paw
python whos-watching.py  # from a source checkout
```

Example output:

```
═══ Media Status — 2026-04-04 20:15:00 ═══

┌─ Jellyfin ─────────────────────────
  1. Alice on Jellyfin Web (Living Room TV)
     ▶  Playing: Breaking Bad — Ozymandias
     Progress: 00:32:15 / 00:47:12 (68%)

┌─ Encoding (media-host) ──────────────
  1. ⚙  Encoding: The.Movie.2024.mkv
     Container: radarr  PID: 1234  Elapsed: 00:08:42

── Streams: 1  Encodes: 1
```

## License

MIT — see [LICENSE](LICENSE).
