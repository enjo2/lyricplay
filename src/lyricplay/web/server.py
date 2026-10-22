"""Launch the local lyricplay web player."""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from collections.abc import Sequence
from urllib.parse import urlencode

from lyricplay import __version__
from lyricplay.errors import DependencyError, LyricPlayError
from lyricplay.web.config import settings


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lyricplay",
        description="Start the local lyricplay web player.",
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="optional search to open in the player",
    )
    parser.add_argument(
        "--host",
        metavar="HOST",
        help="listen address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=_port,
        metavar="PORT",
        help="port (default: 8765)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="print the URL without opening a browser",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def serve(
    *,
    host: str | None = None,
    port: int | None = None,
    open_browser: bool | None = None,
    query: str = "",
) -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - only in a broken install
        raise DependencyError(
            "The web player needs FastAPI and uvicorn. "
            "Install them with: pip install -e ."
        ) from exc

    from lyricplay.web.app import app

    listen_host = host or settings.host
    listen_port = settings.port if port is None else port
    should_open = settings.open_browser if open_browser is None else open_browser
    display_host = "127.0.0.1" if listen_host in {"0.0.0.0", "::"} else listen_host
    url = f"http://{display_host}:{listen_port}/"
    if query.strip():
        url += "?" + urlencode({"q": query.strip()})

    print(f"lyricplay  {url}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if should_open:
        timer = threading.Timer(0.9, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()

    uvicorn.run(
        app,
        host=listen_host,
        port=listen_port,
        log_level="warning",
        access_log=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        serve(
            host=args.host,
            port=args.port,
            open_browser=False if args.no_browser else None,
            query=" ".join(args.query).strip(),
        )
    except LyricPlayError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print()
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
