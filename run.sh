#!/usr/bin/env bash
# Launch the lyricplay web player, creating its virtualenv on first use.
#
#   ./run.sh                         start the player and open your browser
#   ./run.sh --no-browser            print the URL without opening a browser
#   ./run.sh "song name"             start with a search already open
#   ./run.sh --host 0.0.0.0 --port 9000
#
# Everything after the script name is passed to the lyricplay web launcher.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
VENV="$ROOT/.venv"
PYTHON="$VENV/bin/python"

if [[ ! -d "$VENV" ]]; then
    echo "Creating virtualenv in $VENV (first run)..." >&2
    python3 -m venv "$VENV"
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "error: $PYTHON is missing; remove $VENV and run ./run.sh again." >&2
    exit 1
fi

if ! "$PYTHON" -c 'import lyricplay, yt_dlp, fastapi, uvicorn, pydantic_settings' >/dev/null 2>&1; then
    echo "Installing lyricplay and its dependencies..." >&2
    "$PYTHON" -m pip install --quiet --upgrade pip
    "$PYTHON" -m pip install --quiet -e "$ROOT"
fi

exec "$PYTHON" -m lyricplay "$@"
