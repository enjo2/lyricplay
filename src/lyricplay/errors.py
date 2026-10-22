"""Application-specific exceptions."""

from __future__ import annotations


class LyricPlayError(Exception):
    """Base class for errors that should be shown to the user without a traceback."""


class SearchError(LyricPlayError):
    """YouTube search failed."""


class DownloadError(LyricPlayError):
    """Audio download failed."""


class DependencyError(LyricPlayError):
    """A required dependency is missing."""
