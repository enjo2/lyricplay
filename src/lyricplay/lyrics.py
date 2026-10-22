"""Fetch and parse lyrics from LRCLIB (with a plain-lyrics fallback)."""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from lyricplay import __version__

LRCLIB_SEARCH = "https://lrclib.net/api/search"
LRCLIB_GET = "https://lrclib.net/api/get"
LYRICS_OVH = "https://api.lyrics.ovh/v1"
USER_AGENT = f"lyricplay/{__version__} (web player)"


@dataclass(frozen=True, slots=True)
class LyricLine:
    time: float
    text: str


@dataclass(frozen=True, slots=True)
class Lyrics:
    artist: str
    title: str
    synced: tuple[LyricLine, ...] | None
    plain: str
    source: str = "LRCLIB"
    instrumental: bool = False

    @property
    def has_lyrics(self) -> bool:
        return self.instrumental or bool(self.synced or self.plain.strip())


@dataclass(frozen=True, slots=True)
class _Candidate:
    artist: str
    title: str
    duration: float | None
    synced: str
    plain: str
    instrumental: bool
    score: float = 0.0


_TIME_TAG = re.compile(r"\[(\d{1,3}):(\d{2}(?:[.:]\d{1,3})?)\]")
_OFFSET_TAG = re.compile(r"\[offset:\s*([+-]?\d+)\s*\]", re.IGNORECASE)
_META_TAG = re.compile(r"\[(?!\d{1,3}:)[a-zA-Z#]+:[^\]]*\]")
_WORD_TAG = re.compile(r"<\d{1,3}:\d{2}(?:[.:]\d{1,3})?>")
_FEATURED = re.compile(
    r"\s*[\(\[]?\s*(?:feat\.?|ft\.?|featuring)\s+[^)\]]+[\)\]]?\s*$",
    re.IGNORECASE,
)

_CACHE_TTL = 12 * 60 * 60
_CACHE_MAX = 512
_LYRICS_CACHE: OrderedDict[tuple[str, str, int | None], tuple[float, Lyrics | None]] = (
    OrderedDict()
)
_LYRICS_CACHE_LOCK = threading.Lock()
_CACHE_MISS = object()


def clear_lyrics_cache() -> None:
    """Forget cached lookups. Exposed for tests and long-running processes."""

    with _LYRICS_CACHE_LOCK:
        _LYRICS_CACHE.clear()


def _cache_key(title: str, artist: str, duration: float | None) -> tuple[str, str, int | None]:
    rounded = int(round(duration)) if duration and duration > 0 else None
    return (_normalize(artist), _normalize(title), rounded)


def _cache_get(key: tuple[str, str, int | None]) -> Lyrics | None | object:
    now = time.monotonic()
    with _LYRICS_CACHE_LOCK:
        item = _LYRICS_CACHE.get(key)
        if item is None:
            return _CACHE_MISS
        expires_at, value = item
        if expires_at <= now:
            _LYRICS_CACHE.pop(key, None)
            return _CACHE_MISS
        _LYRICS_CACHE.move_to_end(key)
        return value


def _cache_put(key: tuple[str, str, int | None], value: Lyrics | None) -> None:
    with _LYRICS_CACHE_LOCK:
        _LYRICS_CACHE[key] = (time.monotonic() + _CACHE_TTL, value)
        _LYRICS_CACHE.move_to_end(key)
        while len(_LYRICS_CACHE) > _CACHE_MAX:
            _LYRICS_CACHE.popitem(last=False)


def _request_json(url: str, *, params: dict[str, str] | None = None, timeout: float = 12) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Lrclib-Client": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8"))


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = _FEATURED.sub("", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"&", " and ", value)
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _similarity(wanted: str, candidate: str) -> float:
    wanted_n, candidate_n = _normalize(wanted), _normalize(candidate)
    if not wanted_n or not candidate_n:
        return 0.0
    if wanted_n == candidate_n:
        return 1.0
    if wanted_n in candidate_n or candidate_n in wanted_n:
        return 0.94
    wanted_tokens = set(wanted_n.split())
    candidate_tokens = set(candidate_n.split())
    overlap = len(wanted_tokens & candidate_tokens) / len(wanted_tokens | candidate_tokens)
    sequence = SequenceMatcher(None, wanted_n, candidate_n).ratio()
    return max(overlap * 0.96, sequence)


def score_candidate(
    candidate: _Candidate,
    *,
    title: str,
    artist: str,
    duration: float | None,
) -> float:
    title_score = _similarity(title, candidate.title)
    if not title_score and candidate.title:
        # Some LRCLIB entries put "Artist - Title" in trackName.
        title_score = _similarity(title, candidate.title.split(" - ", 1)[-1])
    artist_score = _similarity(artist, candidate.artist) if artist else 0.5
    if duration and candidate.duration and candidate.duration > 0:
        difference = abs(duration - candidate.duration)
        duration_score = max(0.0, 1.0 - difference / 45.0)
    else:
        duration_score = 0.5

    score = (title_score * 0.60) + (artist_score * 0.30) + (duration_score * 0.10)
    if candidate.synced.strip():
        # Exact timestamps are much more valuable than slightly better metadata
        # on a plain-text result: plain lyrics can only ever be approximated.
        score += 0.12
    if candidate.instrumental:
        score -= 0.03
    for keyword in ("karaoke", "cover"):
        if keyword in candidate.title.casefold() and keyword not in title.casefold():
            score -= 0.25
    return score


def _candidate_from_payload(payload: dict[str, Any]) -> _Candidate | None:
    title = str(payload.get("trackName") or payload.get("name") or "").strip()
    artist = str(payload.get("artistName") or "").strip()
    if not title:
        return None
    duration_raw = payload.get("duration")
    duration = float(duration_raw) if isinstance(duration_raw, (int, float)) else None
    return _Candidate(
        artist=artist,
        title=title,
        duration=duration,
        synced=str(payload.get("syncedLyrics") or ""),
        plain=str(payload.get("plainLyrics") or ""),
        instrumental=bool(payload.get("instrumental")),
    )


def _search_lrclib(query: str) -> list[_Candidate]:
    try:
        payload = _request_json(LRCLIB_SEARCH, params={"q": query})
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []
    if not isinstance(payload, list):
        return []
    candidates = [_candidate_from_payload(item) for item in payload if isinstance(item, dict)]
    return [candidate for candidate in candidates if candidate is not None]


def _get_lrclib(title: str, artist: str, duration: float | None) -> _Candidate | None:
    """Try LRCLIB's exact-match endpoint before falling back to search."""

    base = {"track_name": title, "artist_name": artist}
    attempts = [base]
    if duration and duration > 0:
        attempts.insert(0, {**base, "duration": str(int(round(duration)))})
    for params in attempts:
        try:
            payload = _request_json(LRCLIB_GET, params=params)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            continue
        if not isinstance(payload, dict):
            continue
        candidate = _candidate_from_payload(payload)
        if candidate is not None:
            return candidate
    return None


def _best_lrclib_match(
    *,
    title: str,
    artist: str,
    duration: float | None,
) -> _Candidate | None:
    queries = [f"{title} {artist}".strip()]
    if artist:
        queries.append(title)

    candidates: list[_Candidate] = []
    positions: dict[tuple[str, str, float | None], int] = {}

    def add(candidate: _Candidate) -> None:
        key = (candidate.artist.casefold(), candidate.title.casefold(), candidate.duration)
        if key not in positions:
            positions[key] = len(candidates)
            candidates.append(candidate)
            return
        # Prefer the synced copy when the same track appears twice in results.
        index = positions[key]
        if candidate.synced.strip() and not candidates[index].synced.strip():
            candidates[index] = candidate

    # LRCLIB's exact endpoint and the two broad searches are independent. Run
    # them together so a lookup takes roughly as long as the slowest request
    # instead of the sum of three round trips.
    queries = list(dict.fromkeys(queries))
    with ThreadPoolExecutor(max_workers=1 + len(queries)) as pool:
        exact_future = pool.submit(_get_lrclib, title, artist, duration)
        search_futures = [pool.submit(_search_lrclib, query) for query in queries]
        try:
            exact = exact_future.result()
        except Exception:
            exact = None
        if exact is not None:
            add(exact)
        for future in search_futures:
            try:
                found = future.result()
            except Exception:
                found = []
            for candidate in found:
                add(candidate)
    candidates = [
        candidate
        for candidate in candidates
        if candidate.synced.strip() or candidate.plain.strip() or candidate.instrumental
    ]
    if not candidates:
        return None

    scored = [
        (score_candidate(item, title=title, artist=artist, duration=duration), item)
        for item in candidates
    ]
    best_score, best = max(scored, key=lambda pair: pair[0])
    synced = [(score, item) for score, item in scored if item.synced.strip()]
    if synced:
        synced_score, synced_best = max(synced, key=lambda pair: pair[0])
        if synced_score >= 0.52 and synced_score >= best_score - 0.10:
            return synced_best
    if best_score < 0.52:
        return None
    return best


def parse_lrc(value: str) -> tuple[LyricLine, ...] | None:
    """Parse an LRC file, applying offsets and discarding metadata tags."""

    if not value or not value.strip():
        return None
    offset_match = _OFFSET_TAG.search(value)
    offset = int(offset_match.group(1)) / 1000 if offset_match else 0.0
    lines: list[tuple[float, str]] = []
    for raw_line in value.splitlines():
        raw_line = raw_line.strip("\ufeff\r")
        matches = list(_TIME_TAG.finditer(raw_line))
        if not matches:
            continue
        text = _TIME_TAG.sub("", raw_line)
        text = _META_TAG.sub("", text)
        text = _WORD_TAG.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        for match in matches:
            minutes = int(match.group(1))
            seconds = float(match.group(2).replace(":", "."))
            lines.append((max(0.0, minutes * 60 + seconds + offset), text))
    if not lines:
        return None
    lines.sort(key=lambda line: line[0])
    deduped: list[LyricLine] = []
    for timestamp, text in lines:
        if deduped and abs(deduped[-1].time - timestamp) < 0.001 and deduped[-1].text == text:
            continue
        deduped.append(LyricLine(time=timestamp, text=text))
    return tuple(deduped) if deduped else None


def clean_plain_lyrics(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = "\ufeff" + value if not value.startswith("\ufeff") else value
    value = value.lstrip("\ufeff")
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip("\n").strip()


def _lyrics_from_candidate(candidate: _Candidate) -> Lyrics:
    return Lyrics(
        artist=candidate.artist,
        title=candidate.title,
        synced=parse_lrc(candidate.synced),
        plain=clean_plain_lyrics(candidate.plain),
        source="LRCLIB",
        instrumental=candidate.instrumental,
    )


def _lyrics_ovh(title: str, artist: str) -> Lyrics | None:
    if not title.strip():
        return None
    url = f"{LYRICS_OVH}/{urllib.parse.quote(artist, safe='')}/{urllib.parse.quote(title, safe='')}"
    try:
        payload = _request_json(url, timeout=10)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    plain = clean_plain_lyrics(str(payload.get("lyrics") or ""))
    if not plain:
        return None
    return Lyrics(
        artist=artist,
        title=title,
        synced=None,
        plain=plain,
        source="lyrics.ovh",
    )


def _find_lyrics_uncached(
    title: str,
    artist: str,
    *,
    duration: float | None = None,
) -> Lyrics | None:
    candidate = _best_lrclib_match(title=title, artist=artist, duration=duration)
    if candidate is not None and (
        candidate.synced.strip() or candidate.plain.strip() or candidate.instrumental
    ):
        return _lyrics_from_candidate(candidate)
    return _lyrics_ovh(title, artist)


def find_lyrics(
    title: str,
    artist: str,
    *,
    duration: float | None = None,
) -> Lyrics | None:
    """Look up lyrics. Synced LRCLIB lyrics are preferred over plain text.

    Results (including misses) are cached for a few hours. Besides making a
    repeat lookup instant, this keeps the web API from asking LRCLIB for the
    same track on every page load.
    """

    key = _cache_key(title, artist, duration)
    cached = _cache_get(key)
    if cached is not _CACHE_MISS:
        return cached  # type: ignore[return-value]
    result = _find_lyrics_uncached(title, artist, duration=duration)
    _cache_put(key, result)
    return result
