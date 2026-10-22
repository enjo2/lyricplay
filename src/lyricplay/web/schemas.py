"""Pydantic request and response models for the web API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lyricplay.lyrics import LyricLine, Lyrics
from lyricplay.models import SearchResult, Track, format_duration

_VIDEO_ID = r"^[A-Za-z0-9_-]{1,64}$"


def thumbnail_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


class SearchResultOut(BaseModel):
    video_id: str
    raw_title: str
    channel: str
    artist: str
    song: str
    duration: float | None
    duration_label: str
    web_url: str
    thumbnail_url: str

    @classmethod
    def from_result(cls, result: SearchResult) -> SearchResultOut:
        return cls(
            video_id=result.video_id,
            raw_title=result.raw_title,
            channel=result.channel,
            artist=result.artist,
            song=result.song,
            duration=result.duration,
            duration_label=result.duration_label,
            web_url=result.web_url,
            thumbnail_url=thumbnail_url(result.video_id),
        )


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultOut]
    cached: bool
    took_ms: int


class TrackOut(BaseModel):
    video_id: str
    raw_title: str
    channel: str
    artist: str
    title: str
    duration: float | None
    duration_label: str
    web_url: str
    thumbnail_url: str

    @classmethod
    def from_track(cls, track: Track, raw_title: str = "", channel: str = "") -> TrackOut:
        return cls(
            video_id=track.video_id,
            raw_title=raw_title or track.title,
            channel=channel or track.channel,
            artist=track.artist,
            title=track.title,
            duration=track.duration,
            duration_label=format_duration(track.duration),
            web_url=track.web_url,
            thumbnail_url=thumbnail_url(track.video_id),
        )


class LyricLineOut(BaseModel):
    time: float
    text: str

    @classmethod
    def from_line(cls, line: LyricLine) -> LyricLineOut:
        return cls(time=line.time, text=line.text)


class LyricsOut(BaseModel):
    artist: str
    title: str
    synced: list[LyricLineOut] | None
    plain: str
    source: str
    instrumental: bool
    has_lyrics: bool

    @classmethod
    def from_lyrics(cls, lyrics: Lyrics | None) -> LyricsOut | None:
        if lyrics is None:
            return None
        return cls(
            artist=lyrics.artist,
            title=lyrics.title,
            synced=(
                [LyricLineOut.from_line(line) for line in lyrics.synced]
                if lyrics.synced is not None
                else None
            ),
            plain=lyrics.plain,
            source=lyrics.source,
            instrumental=lyrics.instrumental,
            has_lyrics=lyrics.has_lyrics,
        )


class PrepareRequest(BaseModel):
    video_id: str = Field(pattern=_VIDEO_ID)
    raw_title: str = Field(default="", max_length=500)
    channel: str = Field(default="", max_length=300)
    artist: str = Field(default="", max_length=300)
    song: str = Field(min_length=1, max_length=300)
    duration: float | None = Field(default=None, ge=0, le=86400)
    web_url: str = Field(default="", max_length=1000)


class PrepareResponse(BaseModel):
    track: TrackOut
    lyrics: LyricsOut | None
    audio_url: str
    took_ms: int


class LyricsResponse(BaseModel):
    title: str
    artist: str
    lyrics: LyricsOut | None
    took_ms: int


class HealthResponse(BaseModel):
    status: str
    version: str
