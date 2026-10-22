"""Turn messy YouTube titles and channel names into artist / song pairs."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# Words that almost always describe the upload rather than the song itself.
_NOISE = re.compile(
    r"""
    official | lyrics? | lyric\s+video | audio | video | music\s+video |
    visuali[sz]er | remaster(?:ed)? | hd | hq | 4k | 8k | m/v | mv |
    color[-\s]?coded | subtitle[sd]? | captions? | explicit | clean |
    performance | live\s+session | audio\s+only | full\s+song | hdr
    """,
    re.IGNORECASE | re.VERBOSE,
)
_BRACKETED = re.compile(r"[\(\[\{]([^)\]\}]{0,100})[\)\]\}]")
# Only strip a trailing upload label when it follows a real separator. This
# keeps legitimate titles such as "Video Games" intact.
_TRAILING_LABEL = re.compile(
    r"""
    \s*(?:[|•]\s*|[-–—]\s+)
    (?:
        official(?:\s+\w+){0,3} | lyrics? | lyric\s+video | audio |
        music\s+video | video | visuali[sz]er | remaster(?:ed)? |
        hd | hq | 4k | 8k | m/v | mv | full\s+(?:album|song|ep) |
        album | playlist | mix
    )
    (?:\s+.*)?
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)
_TITLE_SEPARATOR = re.compile(r"\s+(?:-|–|—|\||//)\s+")
_FEATURED = re.compile(
    r"\s*[\(\[]?\s*(?:feat\.?|ft\.?|featuring)\s+[^)\]]+[\)\]]?\s*$",
    re.IGNORECASE,
)
_QUOTES = " \t\n\r\"'“”‘’"
_GENERIC_CHANNELS = re.compile(
    r"^(?:youtube|youtube music|vevo|topic|various artists|music|song|songs|lyrics|"
    r"lyric video|official|now playing)$",
    re.IGNORECASE,
)


def _clean_spaces(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u200b", "").replace("\ufeff", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip(_QUOTES)


def _strip_bracketed_noise(title: str) -> str:
    def replace(match: re.Match[str]) -> str:
        content = match.group(1)
        return " " if not content.strip() or _NOISE.search(content) else match.group(0)

    previous = None
    cleaned = title
    while previous != cleaned:
        previous = cleaned
        cleaned = _BRACKETED.sub(replace, cleaned)
    return _clean_spaces(cleaned)


def _channel_name(channel: str) -> str:
    channel = _clean_spaces(channel)
    channel = re.sub(r"\s*[-–—]\s*Topic$", "", channel, flags=re.IGNORECASE)
    channel = re.sub(r"\s*Official$", "", channel, flags=re.IGNORECASE)
    if channel.lower().endswith("vevo") and len(channel) > 4:
        channel = channel[:-4].rstrip()
    return _clean_spaces(channel)


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = _FEATURED.sub("", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _channel_matches(channel: str, candidate: str) -> bool:
    channel_n, candidate_n = _normalized(channel), _normalized(candidate)
    if not channel_n or not candidate_n:
        return False
    if channel_n == candidate_n:
        return True
    if len(candidate_n) >= 4 and (candidate_n in channel_n or channel_n in candidate_n):
        return True
    return SequenceMatcher(None, channel_n, candidate_n).ratio() >= 0.86


def clean_title(title: str) -> str:
    """Remove common upload labels and return the likely song title fragment."""

    title = _clean_spaces(title)
    title = _strip_bracketed_noise(title)
    title = _TRAILING_LABEL.sub("", title)
    title = _clean_spaces(title)
    title = re.sub(r"\s+(?:[-–—|]|//)\s*$", "", title)
    return _clean_spaces(title)


def _strip_featured_for_search(value: str) -> str:
    return _clean_spaces(_FEATURED.sub("", value))


def guess_artist_and_song(
    title: str,
    channel: str = "",
    *,
    metadata_artist: str = "",
    metadata_track: str = "",
) -> tuple[str, str]:
    """Return ``(artist, song)`` for a YouTube video.

    Metadata from YouTube Music is trusted when present. Otherwise the uploader
    channel and common ``Artist - Song`` title patterns are used.
    """

    artist_meta = _clean_spaces(metadata_artist)
    track_meta = _clean_spaces(metadata_track)
    if artist_meta and track_meta:
        return artist_meta, _strip_featured_for_search(track_meta)

    clean = clean_title(title)
    channel_clean = _channel_name(channel)
    parts = _TITLE_SEPARATOR.split(clean, maxsplit=1)
    if len(parts) == 2:
        left, right = (_clean_spaces(part) for part in parts)
        left, right = _strip_featured_for_search(left), _strip_featured_for_search(right)
        if left and right:
            left_match = _channel_matches(channel_clean, left)
            right_match = _channel_matches(channel_clean, right)
            if right_match and not left_match:
                return right, left
            if left_match and not right_match:
                return left, right
            # Most "Artist - Song" uploads place the artist first.
            return left, right

    song = _strip_featured_for_search(clean) or clean_title(title)
    artist = channel_clean
    if not artist or _GENERIC_CHANNELS.match(artist):
        artist = ""
    return artist, song
