# lyricplay

A local web player for music and synced lyrics. Search YouTube, press play, and
follow the words as the song moves — all in your browser.

lyricplay runs on your machine, downloads the audio once, and keeps it in a local
cache. There is no account and no API key; the player talks directly to YouTube
and LRCLIB from your computer.

## What it does

- Searches YouTube from a song name, artist, or lyric.
- Downloads the best audio stream once and caches it locally.
- Finds lyrics through [LRCLIB](https://lrclib.net), preferring timestamped LRC
  lyrics. An exact lookup is tried first, then LRCLIB search.
- Follows synced lyrics line by line, with a small timing nudge for tracks whose
  lyric file was made for a different master.
- Falls back to plain lyrics, paced across the track, when no timestamps exist.
- Keeps a searchable homescreen and recently played tracks in the browser.
- Provides seeking, volume, mute, keyboard controls, and a responsive player.
- Caches searches for 10 minutes and lyric lookups for 12 hours, and fetches
  audio and lyrics at the same time.

## Requirements

- Python 3.11+
- A modern browser with audio output
- An internet connection

`yt-dlp`, FastAPI, uvicorn, and pydantic-settings are installed automatically as
Python dependencies. Keep `yt-dlp` updated if YouTube changes; a recent version
is usually required.

## Quick start

From this folder:

```bash
./run.sh
```

On the first run, `run.sh` creates `.venv`, installs the package and its
dependencies, starts the player at <http://127.0.0.1:8765/>, and opens it in your
browser.

Start with a search already open:

```bash
./run.sh "wish you were here pink floyd"
```

Serve it without opening a browser:

```bash
./run.sh --no-browser
```

If you install the package on your `PATH`, the same options work with the
`lyricplay` command:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/lyricplay
```

## Options

| Option | Meaning |
| --- | --- |
| `--host HOST` | Listen address (default `127.0.0.1`) |
| `--port PORT` | Port (default `8765`) |
| `--no-browser` | Print the URL without opening a browser |
| `--version` | Print the version and exit |
| `"song name"` | Optional initial search to open in the player |

The same defaults can be set with environment variables:

| Variable | Default |
| --- | --- |
| `LYRICPLAY_WEB_HOST` | `127.0.0.1` |
| `LYRICPLAY_WEB_PORT` | `8765` |
| `LYRICPLAY_WEB_OPEN_BROWSER` | `true` |

The server binds to localhost by default and has no authentication. If you pass
`--host 0.0.0.0`, only do so on a trusted network or behind your own access
control.

## Player controls

| Key | Action |
| --- | --- |
| `space` | Play / pause |
| `←` / `→` | Seek back / forward 5 seconds |
| `↑` / `↓` | Volume up / down 5% |
| `m` | Mute / unmute |
| `[` / `]` | Shift lyric timing 0.1 s earlier / later |
| `/` | Focus the search box |
| `esc` | Return to the homescreen |

The same actions are available from the on-screen controls. A volume or sync
change is briefly shown in the player.

## Lyrics

LRCLIB is queried with the artist and song title guessed from the YouTube
upload. An exact lookup is tried first, then LRCLIB search. Synced LRC lyrics are
strongly preferred over plain text, and duplicate results are merged so a synced
copy is not discarded in favour of a plain one.

When synced lyrics are available, the active line is chosen from the LRC
timestamps and the browser's playback position. The display waits for the first
timestamp instead of showing the first line during the intro. A lyric file made
for a different master can be offset by a constant amount; use `[` and `]` to
nudge the timing in 0.1-second steps.

If only plain lyrics are available, one line is advanced at a steady pace across
the track's duration. No karaoke timing is invented because there are no real
timestamps to follow. If LRCLIB has no match, a plain-lyrics fallback via
lyrics.ovh is attempted.

Lyrics can occasionally be wrong for remixes, live versions, or uploads whose
title does not identify the song clearly. Try another search result if the words
do not match.

## Cache

Audio is stored in:

```text
$XDG_CACHE_HOME/lyricplay/audio
```

or `~/.cache/lyricplay/audio` when `XDG_CACHE_HOME` is unset. Songs are cached by
YouTube video ID, so replaying a track is instant. Remove that directory to clear
the audio cache.

The web player also keeps two in-memory caches: search results for 10 minutes and
lyric lookups for 12 hours. They disappear when the server exits.

## Troubleshooting

**YouTube says sign-in is required** — update `yt-dlp`:

```bash
.venv/bin/pip install -U yt-dlp
```

YouTube changes its internals often, so an up-to-date `yt-dlp` matters.

**The port is already in use** — choose another one:

```bash
./run.sh --port 8766
```

**The browser did not open** — open the printed URL manually, or run
`./run.sh --no-browser` and follow the address it prints.

**There is no sound** — check the browser's output device and volume, then make
sure the tab is not muted.

**The display uses fallback fonts** — lyricplay uses Jersey 10 and Space Grotesk
from Google Fonts. The first load needs an internet connection for the fonts; the
player, API, and audio still work without them.

**Lyrics do not match** — the result may be a cover, live version, or a video
with an unhelpful title. Try another result. If the words are right but
consistently early or late, use `[` / `]` to adjust the timing.

## Development

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

The code is split into small modules: `youtube.py` (search and download),
`lyrics.py` (LRCLIB and LRC parsing), `titles.py` (artist and song detection),
and `models.py` (shared data structures). The web player lives in `web/`:
`app.py` (FastAPI routes), `services.py` (caching and preparation), `schemas.py`
(API models), `server.py` (uvicorn launcher), `config.py` (settings), and
`static/` (homescreen, player, CSS, and JavaScript).

## License

lyricplay is MIT-licensed. The web player uses Jersey 10 for display text and
lyrics, and Space Grotesk for interface text. Both fonts are loaded from Google
Fonts; Jersey 10 is licensed under the SIL Open Font License 1.1.
