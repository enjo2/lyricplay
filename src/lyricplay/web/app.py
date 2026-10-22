"""FastAPI application for the local lyricplay web player."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from lyricplay import __version__
from lyricplay.errors import DownloadError, SearchError
from lyricplay.lyrics import clear_lyrics_cache, find_lyrics
from lyricplay.web.schemas import (
    HealthResponse,
    LyricsOut,
    LyricsResponse,
    PrepareRequest,
    PrepareResponse,
    SearchResponse,
    SearchResultOut,
    TrackOut,
)
from lyricplay.web.services import (
    clear_web_caches,
    prepare_track,
    search_tracks,
    track_from_request,
)
from lyricplay.youtube import cached_audio

LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@asynccontextmanager
async def lifespan(_: FastAPI):
    LOGGER.info("lyricplay web player ready")
    yield
    clear_web_caches()
    clear_lyrics_cache()


app = FastAPI(
    title="lyricplay web",
    description="A local, cache-first web player for lyricplay.",
    version=__version__,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data: https://i.ytimg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "script-src 'self'; "
        "media-src 'self' blob:; "
        "connect-src 'self'",
    )
    return response


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@app.get("/api/v1/search", response_model=SearchResponse, tags=["music"])
async def search(
    q: Annotated[str, Query(min_length=1, max_length=160)],
    limit: Annotated[int, Query(ge=1, le=12)] = 8,
) -> SearchResponse:
    query = " ".join(q.split())
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please enter a song name.",
        )

    started = time.perf_counter()
    try:
        results, cached = await search_tracks(query, limit)
    except SearchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return SearchResponse(
        query=query,
        results=[SearchResultOut.from_result(result) for result in results],
        cached=cached,
        took_ms=int((time.perf_counter() - started) * 1000),
    )


@app.post(
    "/api/v1/tracks/prepare",
    response_model=PrepareResponse,
    tags=["music"],
    summary="Download a track and fetch its lyrics",
)
async def prepare(payload: PrepareRequest) -> PrepareResponse:
    started = time.perf_counter()
    try:
        _audio, lyrics = await prepare_track(payload)
    except DownloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    track = track_from_request(payload)
    return PrepareResponse(
        track=TrackOut.from_track(
            track,
            raw_title=payload.raw_title,
            channel=payload.channel,
        ),
        lyrics=LyricsOut.from_lyrics(lyrics),
        audio_url=f"/api/v1/audio/{payload.video_id}",
        took_ms=int((time.perf_counter() - started) * 1000),
    )


@app.get("/api/v1/lyrics", response_model=LyricsResponse, tags=["music"])
async def lyrics(
    title: Annotated[str, Query(min_length=1, max_length=300)],
    artist: Annotated[str, Query(max_length=300)] = "",
    duration: Annotated[float | None, Query(ge=0, le=86400)] = None,
) -> LyricsResponse:
    started = time.perf_counter()
    found = await asyncio.to_thread(find_lyrics, title, artist, duration=duration)
    return LyricsResponse(
        title=title,
        artist=artist,
        lyrics=LyricsOut.from_lyrics(found),
        took_ms=int((time.perf_counter() - started) * 1000),
    )


@app.get("/api/v1/audio/{video_id}", tags=["music"])
async def audio(video_id: str) -> FileResponse:
    if not _VIDEO_ID_RE.fullmatch(video_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown track.")
    path = await asyncio.to_thread(cached_audio, video_id)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio is still being prepared. Try again in a moment.",
        )
    return FileResponse(
        path,
        media_type=None,
        headers={"Cache-Control": "private, max-age=86400"},
    )
