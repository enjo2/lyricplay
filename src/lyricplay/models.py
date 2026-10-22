"""Shared data structures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One YouTube search result, with a human-friendly artist/song guess."""

    video_id: str
    raw_title: str
    channel: str
    artist: str
    song: str
    duration: float | None
    web_url: str

    @property
    def duration_label(self) -> str:
        return format_duration(self.duration)


@dataclass(frozen=True, slots=True)
class Track:
    """The track being played."""

    artist: str
    title: str
    video_id: str
    duration: float | None = None
    web_url: str = ""
    channel: str = ""


@dataclass(frozen=True, slots=True)
class Audio:
    """A playable local audio file."""

    path: Path
    video_id: str


def format_duration(seconds: float | None) -> str:
    """Format seconds as ``m:ss`` or ``h:mm:ss``."""

    if not seconds or seconds <= 0:
        return ""
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
