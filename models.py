"""Pydantic models/schemas for the YouTube Music API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Generic wrapper
# ---------------------------------------------------------------------------

class APIResponse(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchResult(BaseModel):
    videoId: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    duration: Optional[str] = None
    duration_seconds: Optional[int] = None
    thumbnail: Optional[str] = None
    url: Optional[str] = None
    isLive: bool = False
    views: Optional[str] = None
    explicit: bool = False
    resultType: Optional[str] = None


class SearchResponse(BaseModel):
    success: bool = True
    data: list[SearchResult] = []
    error: Optional[str] = None
    total: int = 0


class SuggestionResponse(BaseModel):
    success: bool = True
    data: list[str] = []
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Video / Song details
# ---------------------------------------------------------------------------

class VideoInfo(BaseModel):
    videoId: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    duration: Optional[str] = None
    duration_seconds: Optional[int] = None
    thumbnail: Optional[str] = None
    description: Optional[str] = None
    uploadDate: Optional[str] = None
    views: Optional[str] = None
    likes: Optional[str] = None
    isLive: bool = False
    webpage_url: Optional[str] = None
    relatedVideos: list[dict] = []


class LyricsResponse(BaseModel):
    success: bool = True
    data: Optional[dict] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Artist / Playlist / Album
# ---------------------------------------------------------------------------

class ArtistInfo(BaseModel):
    name: Optional[str] = None
    browseId: Optional[str] = None
    description: Optional[str] = None
    thumbnail: Optional[str] = None
    topSongs: list[dict] = []
    albums: list[dict] = []
    singles: list[dict] = []


class PlaylistInfo(BaseModel):
    playlistId: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    thumbnail: Optional[str] = None
    author: Optional[str] = None
    trackCount: Optional[int] = None
    tracks: list[dict] = []


class AlbumInfo(BaseModel):
    albumId: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    year: Optional[str] = None
    thumbnail: Optional[str] = None
    trackCount: Optional[int] = None
    tracks: list[dict] = []


# ---------------------------------------------------------------------------
# Stream / Download
# ---------------------------------------------------------------------------

class StreamInfo(BaseModel):
    videoId: str
    url: Optional[str] = None
    format: Optional[str] = None
    quality: Optional[str] = None
    filesize: Optional[int] = None
    ext: Optional[str] = None
    title: Optional[str] = None


class BatchStreamRequest(BaseModel):
    videoIds: list[str] = Field(..., min_length=1, max_length=10)


# ---------------------------------------------------------------------------
# Advanced search
# ---------------------------------------------------------------------------

class AdvancedSearchFilters(BaseModel):
    duration: Optional[str] = None  # "short" | "long" | "medium"
    type: Optional[str] = None      # "song" | "video" | "playlist"
    uploadDate: Optional[str] = None


class AdvancedSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    filters: Optional[AdvancedSearchFilters] = None
    limit: int = Field(default=20, ge=1, le=50)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class StatsResponse(BaseModel):
    success: bool = True
    data: dict = {}
    error: Optional[str] = None
