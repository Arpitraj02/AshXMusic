"""
AshXMusic – Comprehensive No-Auth YouTube Music API
====================================================
FastAPI backend for Telegram music bots.
No API keys required – powered by yt-dlp & ytmusicapi.

Run:
    pip install -r requirements.txt
    python main.py
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import random
import time
import zipfile
from contextlib import asynccontextmanager
from typing import Any, Optional

import yt_dlp
from cachetools import TTLCache
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from ytmusicapi import YTMusic

from models import (
    AdvancedSearchRequest,
    AlbumInfo,
    APIResponse,
    ArtistInfo,
    BatchStreamRequest,
    LyricsResponse,
    PlaylistInfo,
    SearchResponse,
    SearchResult,
    StatsResponse,
    StreamInfo,
    SuggestionResponse,
    VideoInfo,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv()

HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ashxmusic")

# ---------------------------------------------------------------------------
# In-memory caches  (TTL = 300 s, max 512 entries)
# ---------------------------------------------------------------------------

_search_cache: TTLCache = TTLCache(maxsize=512, ttl=300)
_info_cache: TTLCache = TTLCache(maxsize=256, ttl=600)
_stream_cache: TTLCache = TTLCache(maxsize=128, ttl=120)

_cache_hits: int = 0
_cache_misses: int = 0
_start_time: float = time.time()

# ---------------------------------------------------------------------------
# Global ytmusicapi client (no-auth, anonymous)
# ---------------------------------------------------------------------------

ytmusic: YTMusic = YTMusic()

# ---------------------------------------------------------------------------
# Rate limiter  (10 req / sec per IP)
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address, default_limits=["10/second"])


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AshXMusic API starting up…")
    yield
    logger.info("AshXMusic API shutting down…")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AshXMusic API",
    description=(
        "Comprehensive no-auth YouTube Music API for Telegram bots. "
        "Powered by yt-dlp & ytmusicapi. No API keys required."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _yt_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _thumb(video_id: str, quality: str = "hqdefault") -> str:
    return f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg"


def _extract_thumbnail(thumbnails: list[dict] | None) -> str:
    if not thumbnails:
        return ""
    return thumbnails[-1].get("url", "")


def _duration_str(seconds: int | None) -> str:
    if not seconds:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


async def _run_ydl(opts: dict, url: str) -> dict:
    """Run yt-dlp extraction in a thread to avoid blocking the event loop."""
    def _extract():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    return await asyncio.to_thread(_extract)


def _safe_str_views(info: dict) -> str:
    v = info.get("view_count")
    if v is None:
        return "N/A"
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.1f}K"
    return str(v)


def _map_ytmusic_result(item: dict) -> SearchResult:
    """Map a ytmusicapi result dict to a SearchResult."""
    video_id = item.get("videoId") or item.get("browseId") or ""
    artists = item.get("artists") or []
    artist_name = ", ".join(a.get("name", "") for a in artists) if artists else item.get("artist", "")
    album_info = item.get("album") or {}
    duration_secs = item.get("duration_seconds")
    thumbnails = item.get("thumbnails") or []
    return SearchResult(
        videoId=video_id,
        title=item.get("title") or item.get("name") or "",
        artist=artist_name,
        album=album_info.get("name") if isinstance(album_info, dict) else str(album_info),
        duration=item.get("duration") or _duration_str(duration_secs),
        duration_seconds=duration_secs,
        thumbnail=_extract_thumbnail(thumbnails) or (_thumb(video_id) if video_id else ""),
        url=_yt_url(video_id) if video_id else "",
        isLive=item.get("isLive", False),
        views=str(item.get("views", "N/A")),
        explicit=item.get("isExplicit", False),
        resultType=item.get("resultType", ""),
    )


# ---------------------------------------------------------------------------
# Health / Stats
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Utility"])
async def health():
    return {"success": True, "data": {"status": "ok", "version": "1.0.0"}}


@app.get("/stats", tags=["Utility"], response_model=StatsResponse)
async def stats():
    global _cache_hits, _cache_misses
    uptime = time.time() - _start_time
    return StatsResponse(
        success=True,
        data={
            "uptime_seconds": round(uptime, 2),
            "cache_hits": _cache_hits,
            "cache_misses": _cache_misses,
            "search_cache_size": len(_search_cache),
            "info_cache_size": len(_info_cache),
            "stream_cache_size": len(_stream_cache),
        },
    )


# ---------------------------------------------------------------------------
# 1. SEARCH ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/search", tags=["Search"], response_model=SearchResponse)
@limiter.limit("10/second")
async def search(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    type: str = Query("song", description="song | video | playlist | artist | album"),
    limit: int = Query(20, ge=1, le=50),
):
    """Search YouTube Music for songs, videos, playlists, artists, or albums."""
    global _cache_hits, _cache_misses
    cache_key = f"search:{q}:{type}:{limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return SearchResponse(success=True, data=_search_cache[cache_key], total=len(_search_cache[cache_key]))
    _cache_misses += 1

    filter_map = {
        "song": "songs",
        "video": "videos",
        "playlist": "playlists",
        "artist": "artists",
        "album": "albums",
    }
    yt_filter = filter_map.get(type, "songs")
    try:
        results = await asyncio.to_thread(ytmusic.search, q, filter=yt_filter, limit=limit)
        mapped = [_map_ytmusic_result(r) for r in (results or [])]
        _search_cache[cache_key] = mapped
        return SearchResponse(success=True, data=mapped, total=len(mapped))
    except Exception as exc:
        logger.error("search error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/search/suggestions", tags=["Search"], response_model=SuggestionResponse)
@limiter.limit("10/second")
async def search_suggestions(
    request: Request,
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=20),
):
    """Get autocomplete / search suggestions."""
    global _cache_hits, _cache_misses
    cache_key = f"suggestions:{q}:{limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return SuggestionResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        suggestions = await asyncio.to_thread(ytmusic.get_search_suggestions, q)
        data = (suggestions or [])[:limit]
        _search_cache[cache_key] = data
        return SuggestionResponse(success=True, data=data)
    except Exception as exc:
        logger.error("suggestions error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/search/related", tags=["Search"])
@limiter.limit("10/second")
async def search_related(
    request: Request,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
):
    """Get related search queries."""
    global _cache_hits, _cache_misses
    cache_key = f"related:{q}:{limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        suggestions = await asyncio.to_thread(ytmusic.get_search_suggestions, q)
        data = (suggestions or [])[:limit]
        _search_cache[cache_key] = data
        return APIResponse(success=True, data=data)
    except Exception as exc:
        logger.error("related error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/search/trending", tags=["Search"])
@limiter.limit("10/second")
async def search_trending(
    request: Request,
    category: str = Query("music", description="music | pop | rock | global"),
    limit: int = Query(20, ge=1, le=50),
):
    """Get trending songs/videos."""
    global _cache_hits, _cache_misses
    cache_key = f"trending:{category}:{limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        results = await asyncio.to_thread(ytmusic.search, f"trending {category} music 2024", filter="songs", limit=limit)
        mapped = [_map_ytmusic_result(r) for r in (results or [])]
        _search_cache[cache_key] = [m.model_dump() for m in mapped]
        return APIResponse(success=True, data=_search_cache[cache_key])
    except Exception as exc:
        logger.error("trending error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/search/charts", tags=["Search"])
@limiter.limit("10/second")
async def search_charts(
    request: Request,
    country: str = Query("US", description="ISO country code e.g. US, IN, GB"),
    limit: int = Query(20, ge=1, le=50),
):
    """Get YouTube Music charts by country."""
    global _cache_hits, _cache_misses
    cache_key = f"charts:{country}:{limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        charts = await asyncio.to_thread(ytmusic.get_charts, country=country)
        data: dict[str, Any] = {}
        if charts:
            videos_section = charts.get("videos") or {}
            items = videos_section.get("items") or []
            data["videos"] = items[:limit]
            trending_section = charts.get("trending") or {}
            trend_items = trending_section.get("items") or []
            data["trending"] = trend_items[:limit]
            artists_section = charts.get("artists") or {}
            artist_items = artists_section.get("items") or []
            data["artists"] = artist_items[:limit]
        _search_cache[cache_key] = data
        return APIResponse(success=True, data=data)
    except Exception as exc:
        logger.error("charts error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 2. VIDEO / SONG DETAIL ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/video/info", tags=["Video"])
@limiter.limit("10/second")
async def video_info(
    request: Request,
    videoId: str = Query(..., min_length=5),
):
    """Get rich metadata for a video/song."""
    global _cache_hits, _cache_misses
    cache_key = f"info:{videoId}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    try:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        info = await _run_ydl(opts, _yt_url(videoId))
        thumbnails = info.get("thumbnails") or []
        related = []
        for e in (info.get("entries") or [])[:5]:
            related.append({
                "videoId": e.get("id"),
                "title": e.get("title"),
                "thumbnail": _thumb(e.get("id", "")),
            })
        result = VideoInfo(
            videoId=info.get("id", videoId),
            title=info.get("title"),
            artist=info.get("uploader") or info.get("channel"),
            album=info.get("album"),
            duration=_duration_str(info.get("duration")),
            duration_seconds=info.get("duration"),
            thumbnail=_extract_thumbnail(thumbnails) or _thumb(videoId),
            description=(info.get("description") or "")[:500],
            uploadDate=info.get("upload_date"),
            views=_safe_str_views(info),
            likes=str(info.get("like_count", "N/A")),
            isLive=info.get("is_live", False),
            webpage_url=info.get("webpage_url", _yt_url(videoId)),
            relatedVideos=related,
        ).model_dump()
        _info_cache[cache_key] = result
        return APIResponse(success=True, data=result)
    except Exception as exc:
        logger.error("video_info error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/video/thumbnail", tags=["Video"])
@limiter.limit("10/second")
async def video_thumbnail(
    request: Request,
    videoId: str = Query(..., min_length=5),
    quality: str = Query("hqdefault", description="maxresdefault | hqdefault | mqdefault | default"),
):
    """Redirect to a YouTube thumbnail URL."""
    allowed = {"maxresdefault", "hqdefault", "mqdefault", "sddefault", "default"}
    q = quality if quality in allowed else "hqdefault"
    url = _thumb(videoId, q)
    return RedirectResponse(url=url)


@app.get("/video/lyrics", tags=["Video"], response_model=LyricsResponse)
@limiter.limit("10/second")
async def video_lyrics(
    request: Request,
    videoId: str = Query(..., min_length=5),
):
    """Get lyrics for a song via ytmusicapi (if available)."""
    global _cache_hits, _cache_misses
    cache_key = f"lyrics:{videoId}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return LyricsResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    try:
        watch_playlist = await asyncio.to_thread(ytmusic.get_watch_playlist, videoId=videoId)
        lyrics_browse_id = (watch_playlist or {}).get("lyrics")
        if not lyrics_browse_id:
            return LyricsResponse(success=True, data=None, error="Lyrics not available for this track.")
        lyrics = await asyncio.to_thread(ytmusic.get_lyrics, lyrics_browse_id)
        _info_cache[cache_key] = lyrics
        return LyricsResponse(success=True, data=lyrics)
    except Exception as exc:
        logger.error("lyrics error: %s", exc)
        return LyricsResponse(success=False, data=None, error=str(exc))


# ---------------------------------------------------------------------------
# 3. ARTIST ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/artist/info", tags=["Artist"])
@limiter.limit("10/second")
async def artist_info(
    request: Request,
    browseId: str = Query(..., min_length=5),
    limit: int = Query(20, ge=1, le=50),
):
    """Get artist information including top songs, albums, and bio."""
    global _cache_hits, _cache_misses
    cache_key = f"artist:{browseId}:{limit}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    try:
        info = await asyncio.to_thread(ytmusic.get_artist, browseId)
        thumbnails = (info or {}).get("thumbnails") or []
        top_songs_section = (info or {}).get("songs") or {}
        top_songs = (top_songs_section.get("results") or [])[:limit]
        albums_section = (info or {}).get("albums") or {}
        albums = (albums_section.get("results") or [])[:limit]
        singles_section = (info or {}).get("singles") or {}
        singles = (singles_section.get("results") or [])[:limit]
        result = ArtistInfo(
            name=info.get("name"),
            browseId=browseId,
            description=info.get("description"),
            thumbnail=_extract_thumbnail(thumbnails),
            topSongs=top_songs,
            albums=albums,
            singles=singles,
        ).model_dump()
        _info_cache[cache_key] = result
        return APIResponse(success=True, data=result)
    except Exception as exc:
        logger.error("artist_info error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/top/artists", tags=["Artist"])
@limiter.limit("10/second")
async def top_artists(
    request: Request,
    country: str = Query("US"),
    limit: int = Query(20, ge=1, le=50),
):
    """Get top artists from YouTube Music charts."""
    global _cache_hits, _cache_misses
    cache_key = f"top_artists:{country}:{limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        charts = await asyncio.to_thread(ytmusic.get_charts, country=country)
        artists_section = (charts or {}).get("artists") or {}
        items = (artists_section.get("items") or [])[:limit]
        _search_cache[cache_key] = items
        return APIResponse(success=True, data=items)
    except Exception as exc:
        logger.error("top_artists error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 4. PLAYLIST ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/playlist/info", tags=["Playlist"])
@limiter.limit("10/second")
async def playlist_info(
    request: Request,
    playlistId: str = Query(..., min_length=5),
    limit: int = Query(50, ge=1, le=100),
):
    """Get playlist details and tracks."""
    global _cache_hits, _cache_misses
    cache_key = f"playlist:{playlistId}:{limit}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    try:
        pl = await asyncio.to_thread(ytmusic.get_playlist, playlistId, limit=limit)
        thumbnails = (pl or {}).get("thumbnails") or []
        tracks = (pl or {}).get("tracks") or []
        author = (pl or {}).get("author") or {}
        result = PlaylistInfo(
            playlistId=playlistId,
            title=pl.get("title"),
            description=pl.get("description"),
            thumbnail=_extract_thumbnail(thumbnails),
            author=author.get("name") if isinstance(author, dict) else str(author),
            trackCount=pl.get("trackCount"),
            tracks=tracks[:limit],
        ).model_dump()
        _info_cache[cache_key] = result
        return APIResponse(success=True, data=result)
    except Exception as exc:
        logger.error("playlist_info error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 5. ALBUM ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/album/info", tags=["Album"])
@limiter.limit("10/second")
async def album_info(
    request: Request,
    albumId: str = Query(..., min_length=5),
    limit: int = Query(50, ge=1, le=100),
):
    """Get album details and tracks."""
    global _cache_hits, _cache_misses
    cache_key = f"album:{albumId}:{limit}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    try:
        album = await asyncio.to_thread(ytmusic.get_album, albumId)
        thumbnails = (album or {}).get("thumbnails") or []
        tracks = (album or {}).get("tracks") or []
        artists = (album or {}).get("artists") or []
        artist_name = ", ".join(a.get("name", "") for a in artists)
        result = AlbumInfo(
            albumId=albumId,
            title=album.get("title"),
            artist=artist_name,
            year=str(album.get("year") or ""),
            thumbnail=_extract_thumbnail(thumbnails),
            trackCount=album.get("trackCount"),
            tracks=tracks[:limit],
        ).model_dump()
        _info_cache[cache_key] = result
        return APIResponse(success=True, data=result)
    except Exception as exc:
        logger.error("album_info error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 6. AUDIO STREAM / DOWNLOAD ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/audio/stream", tags=["Audio"])
@limiter.limit("10/second")
async def audio_stream(
    request: Request,
    videoId: str = Query(..., min_length=5),
    format: str = Query("best", description="mp3 | opus | best"),
):
    """
    Stream audio directly from YouTube.
    Supports HTTP Range requests for partial content (seek support).
    """
    global _cache_hits, _cache_misses
    cache_key = f"audio_stream:{videoId}:{format}"
    audio_url: Optional[str] = None

    if cache_key in _stream_cache:
        _cache_hits += 1
        audio_url = _stream_cache[cache_key]
    else:
        _cache_misses += 1
        format_selector = "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best"
        if format == "mp3":
            format_selector = "bestaudio[acodec=mp3]/bestaudio/best"
        elif format == "opus":
            format_selector = "bestaudio[acodec=opus]/bestaudio/best"

        opts = {
            "quiet": True,
            "no_warnings": True,
            "format": format_selector,
            "skip_download": True,
        }
        try:
            info = await _run_ydl(opts, _yt_url(videoId))
            audio_url = info.get("url")
            if audio_url:
                _stream_cache[cache_key] = audio_url
        except Exception as exc:
            logger.error("audio_stream extract error: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    if not audio_url:
        raise HTTPException(status_code=404, detail="Audio stream URL not found.")

    return RedirectResponse(url=audio_url)


@app.get("/audio/download", tags=["Audio"])
@limiter.limit("10/second")
async def audio_download(
    request: Request,
    videoId: str = Query(..., min_length=5),
):
    """
    Stream audio bytes directly (downloads to client as MP3/WebM).
    Use /audio/stream for Telegram bots (redirect is faster).
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "skip_download": True,
    }
    try:
        info = await _run_ydl(opts, _yt_url(videoId))
        audio_url = info.get("url")
        title = info.get("title", videoId)
        ext = info.get("ext", "webm")
        if not audio_url:
            raise HTTPException(status_code=404, detail="No audio URL found.")

        import httpx
        async def stream_audio():
            async with httpx.AsyncClient(follow_redirects=True) as client:
                async with client.stream("GET", audio_url) as resp:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        yield chunk

        return StreamingResponse(
            stream_audio(),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f'attachment; filename="{title}.{ext}"',
                "Accept-Ranges": "bytes",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("audio_download error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/audio/info", tags=["Audio"])
@limiter.limit("10/second")
async def audio_info(
    request: Request,
    videoId: str = Query(..., min_length=5),
    format: str = Query("best", description="mp3 | opus | best"),
):
    """Get direct audio stream URL and metadata without redirecting."""
    global _cache_hits, _cache_misses
    cache_key = f"audio_info:{videoId}:{format}"
    if cache_key in _stream_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_stream_cache[cache_key])
    _cache_misses += 1

    format_selector = "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best"
    if format == "mp3":
        format_selector = "bestaudio[acodec=mp3]/bestaudio/best"
    elif format == "opus":
        format_selector = "bestaudio[acodec=opus]/bestaudio/best"

    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": format_selector,
        "skip_download": True,
    }
    try:
        info = await _run_ydl(opts, _yt_url(videoId))
        result = StreamInfo(
            videoId=videoId,
            url=info.get("url"),
            format=info.get("acodec"),
            quality=info.get("abr"),
            filesize=info.get("filesize"),
            ext=info.get("ext"),
            title=info.get("title"),
        ).model_dump()
        _stream_cache[cache_key] = result
        return APIResponse(success=True, data=result)
    except Exception as exc:
        logger.error("audio_info error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 7. VIDEO STREAM ENDPOINT
# ---------------------------------------------------------------------------

@app.get("/video/stream", tags=["Video"])
@limiter.limit("10/second")
async def video_stream(
    request: Request,
    videoId: str = Query(..., min_length=5),
    quality: str = Query("best", description="best | worst | 360p | 720p | 1080p"),
):
    """Redirect to a direct video stream URL."""
    global _cache_hits, _cache_misses
    cache_key = f"video_stream:{videoId}:{quality}"
    if cache_key in _stream_cache:
        _cache_hits += 1
        return RedirectResponse(url=_stream_cache[cache_key])
    _cache_misses += 1

    quality_map = {
        "worst": "worstvideo+worstaudio/worst",
        "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "best": "bestvideo+bestaudio/best",
    }
    fmt = quality_map.get(quality, "bestvideo+bestaudio/best")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": fmt,
        "skip_download": True,
    }
    try:
        info = await _run_ydl(opts, _yt_url(videoId))
        video_url = info.get("url") or (info.get("requested_formats") or [{}])[0].get("url")
        if not video_url:
            raise HTTPException(status_code=404, detail="Video stream URL not found.")
        _stream_cache[cache_key] = video_url
        return RedirectResponse(url=video_url)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("video_stream error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 8. BATCH STREAM ENDPOINT
# ---------------------------------------------------------------------------

@app.post("/batch/stream", tags=["Audio"])
@limiter.limit("5/second")
async def batch_stream(request: Request, body: BatchStreamRequest):
    """
    Get stream URLs for multiple videos at once.
    Returns a list of {videoId, url, title, ext} objects.
    """
    results = []
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "skip_download": True,
    }

    async def _get_one(vid: str) -> dict:
        cache_key = f"audio_stream:{vid}:best"
        if cache_key in _stream_cache:
            return {"videoId": vid, "url": _stream_cache[cache_key], "cached": True}
        try:
            info = await _run_ydl(opts, _yt_url(vid))
            url = info.get("url", "")
            if url:
                _stream_cache[cache_key] = url
            return {"videoId": vid, "url": url, "title": info.get("title"), "ext": info.get("ext"), "cached": False}
        except Exception as exc:
            return {"videoId": vid, "url": None, "error": str(exc)}

    tasks = [_get_one(vid) for vid in body.videoIds]
    results = await asyncio.gather(*tasks)
    return APIResponse(success=True, data=list(results))


# ---------------------------------------------------------------------------
# 9. YOUTUBE MUSIC SPECIFIC ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/ytmusic/search", tags=["YTMusic"])
@limiter.limit("10/second")
async def ytmusic_search(
    request: Request,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
):
    """YouTube Music-specific search (all types)."""
    global _cache_hits, _cache_misses
    cache_key = f"ytmusic_search:{q}:{limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        results = await asyncio.to_thread(ytmusic.search, q, limit=limit)
        mapped = [_map_ytmusic_result(r).model_dump() for r in (results or [])]
        _search_cache[cache_key] = mapped
        return APIResponse(success=True, data=mapped)
    except Exception as exc:
        logger.error("ytmusic_search error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/ytmusic/home", tags=["YTMusic"])
@limiter.limit("10/second")
async def ytmusic_home(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
):
    """Get YouTube Music home feed (shelves, charts, moods)."""
    global _cache_hits, _cache_misses
    cache_key = f"ytmusic_home:{limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        home = await asyncio.to_thread(ytmusic.get_home, limit=limit)
        _search_cache[cache_key] = home or []
        return APIResponse(success=True, data=home or [])
    except Exception as exc:
        logger.error("ytmusic_home error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/ytmusic/library", tags=["YTMusic"])
@limiter.limit("10/second")
async def ytmusic_library(
    request: Request,
    type: str = Query("songs", description="songs | playlists | artists"),
    limit: int = Query(20, ge=1, le=50),
):
    """Simulated library – returns popular items of the chosen type."""
    global _cache_hits, _cache_misses
    cache_key = f"ytmusic_library:{type}:{limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    query_map = {"songs": "popular songs 2024", "playlists": "best playlist 2024", "artists": "top artists 2024"}
    filter_map = {"songs": "songs", "playlists": "playlists", "artists": "artists"}
    q = query_map.get(type, "popular songs 2024")
    f = filter_map.get(type, "songs")
    try:
        results = await asyncio.to_thread(ytmusic.search, q, filter=f, limit=limit)
        mapped = [_map_ytmusic_result(r).model_dump() for r in (results or [])]
        _search_cache[cache_key] = mapped
        return APIResponse(success=True, data=mapped)
    except Exception as exc:
        logger.error("ytmusic_library error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/ytmusic/browse", tags=["YTMusic"])
@limiter.limit("10/second")
async def ytmusic_browse(
    request: Request,
    browseId: str = Query(..., min_length=5),
):
    """Browse a YouTube Music category by browseId."""
    global _cache_hits, _cache_misses
    cache_key = f"ytmusic_browse:{browseId}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        result = await asyncio.to_thread(ytmusic.get_artist, browseId)
        _search_cache[cache_key] = result or {}
        return APIResponse(success=True, data=result or {})
    except Exception as exc:
        logger.error("ytmusic_browse error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/ytmusic/get_search_suggestions", tags=["YTMusic"])
@limiter.limit("10/second")
async def ytmusic_get_search_suggestions(
    request: Request,
    q: str = Query(..., min_length=1),
):
    """Get YouTube Music-specific search suggestions."""
    global _cache_hits, _cache_misses
    cache_key = f"ytmusic_sugg:{q}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return SuggestionResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        suggestions = await asyncio.to_thread(ytmusic.get_search_suggestions, q)
        data = suggestions or []
        _search_cache[cache_key] = data
        return SuggestionResponse(success=True, data=data)
    except Exception as exc:
        logger.error("ytmusic suggestions error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 10. RELATED VIDEOS
# ---------------------------------------------------------------------------

@app.get("/related/videos", tags=["Related"])
@limiter.limit("10/second")
async def related_videos(
    request: Request,
    videoId: str = Query(..., min_length=5),
    limit: int = Query(20, ge=1, le=50),
):
    """Get recommended/related videos for a given videoId."""
    global _cache_hits, _cache_misses
    cache_key = f"related_videos:{videoId}:{limit}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    try:
        watch_pl = await asyncio.to_thread(ytmusic.get_watch_playlist, videoId=videoId, limit=limit)
        tracks = (watch_pl or {}).get("tracks") or []
        result = [_map_ytmusic_result(t).model_dump() for t in tracks[:limit]]
        _info_cache[cache_key] = result
        return APIResponse(success=True, data=result)
    except Exception as exc:
        logger.error("related_videos error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 11. RANDOM SONG
# ---------------------------------------------------------------------------

_GENRES = {
    "pop": "top pop songs 2024",
    "rock": "top rock songs 2024",
    "hiphop": "top hip hop songs 2024",
    "jazz": "top jazz songs",
    "electronic": "top electronic music 2024",
    "classical": "best classical music",
    "any": "top songs 2024",
}


@app.get("/random/song", tags=["Utility"])
@limiter.limit("10/second")
async def random_song(
    request: Request,
    genre: str = Query("any", description="any | pop | rock | hiphop | jazz | electronic | classical"),
):
    """Get a random popular song (optionally filtered by genre)."""
    query = _GENRES.get(genre, _GENRES["any"])
    try:
        results = await asyncio.to_thread(ytmusic.search, query, filter="songs", limit=50)
        if not results:
            raise HTTPException(status_code=404, detail="No results found.")
        song = random.choice(results)
        return APIResponse(success=True, data=_map_ytmusic_result(song).model_dump())
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("random_song error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 12. GENRE BROWSE
# ---------------------------------------------------------------------------

@app.get("/genre/browse", tags=["Utility"])
@limiter.limit("10/second")
async def genre_browse(
    request: Request,
    genre: str = Query("pop", description="pop | rock | hiphop | jazz | electronic | classical"),
    limit: int = Query(20, ge=1, le=50),
):
    """Browse songs by genre."""
    query = _GENRES.get(genre, f"top {genre} songs 2024")
    global _cache_hits, _cache_misses
    cache_key = f"genre:{genre}:{limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        results = await asyncio.to_thread(ytmusic.search, query, filter="songs", limit=limit)
        mapped = [_map_ytmusic_result(r).model_dump() for r in (results or [])]
        _search_cache[cache_key] = mapped
        return APIResponse(success=True, data=mapped)
    except Exception as exc:
        logger.error("genre_browse error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 13. LIVE STREAMS
# ---------------------------------------------------------------------------

@app.get("/live/streams", tags=["Utility"])
@limiter.limit("10/second")
async def live_streams(
    request: Request,
    category: str = Query("music", description="music | pop | rock | news"),
    limit: int = Query(20, ge=1, le=50),
):
    """Get live music streams from YouTube."""
    global _cache_hits, _cache_misses
    cache_key = f"live:{category}:{limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
    }
    try:
        search_url = f"ytsearch{limit}:{category} music live stream"
        info = await _run_ydl(opts, search_url)
        entries = info.get("entries") or []
        results = []
        for e in entries:
            results.append({
                "videoId": e.get("id"),
                "title": e.get("title"),
                "thumbnail": _thumb(e.get("id", "")),
                "url": _yt_url(e.get("id", "")),
                "isLive": e.get("is_live", False),
                "views": str(e.get("view_count", "N/A")),
                "uploader": e.get("uploader"),
            })
        _search_cache[cache_key] = results
        return APIResponse(success=True, data=results)
    except Exception as exc:
        logger.error("live_streams error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 14. ADVANCED SEARCH
# ---------------------------------------------------------------------------

@app.post("/search/advanced", tags=["Search"])
@limiter.limit("10/second")
async def search_advanced(request: Request, body: AdvancedSearchRequest):
    """Advanced search with filters (duration, type, etc.)."""
    global _cache_hits, _cache_misses
    filters = body.filters or AdvancedSearchFilters()
    search_type = (filters.type or "song").lower()
    filter_map = {
        "song": "songs",
        "songs": "songs",
        "video": "videos",
        "videos": "videos",
        "playlist": "playlists",
        "playlists": "playlists",
        "artist": "artists",
        "artists": "artists",
        "album": "albums",
        "albums": "albums",
    }
    yt_filter = filter_map.get(search_type, "songs")
    cache_key = f"advanced:{body.query}:{search_type}:{body.limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        results = await asyncio.to_thread(ytmusic.search, body.query, filter=yt_filter, limit=body.limit)
        mapped = [_map_ytmusic_result(r).model_dump() for r in (results or [])]

        # Apply duration filter post-search
        if filters.duration and mapped:
            def _dur_filter(item: dict) -> bool:
                secs = item.get("duration_seconds") or 0
                if filters.duration == "short":
                    return secs < 240        # < 4 min
                if filters.duration == "long":
                    return secs > 1200       # > 20 min
                if filters.duration == "medium":
                    return 240 <= secs <= 1200
                return True
            mapped = [m for m in mapped if _dur_filter(m)]

        _search_cache[cache_key] = mapped
        return APIResponse(success=True, data=mapped)
    except Exception as exc:
        logger.error("advanced_search error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 15. MOOD / PLAYLIST BROWSE
# ---------------------------------------------------------------------------

@app.get("/ytmusic/moods", tags=["YTMusic"])
@limiter.limit("10/second")
async def ytmusic_moods(request: Request):
    """Get mood/genre categories from YouTube Music."""
    global _cache_hits, _cache_misses
    cache_key = "ytmusic_moods"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        moods = await asyncio.to_thread(ytmusic.get_mood_categories)
        _search_cache[cache_key] = moods or {}
        return APIResponse(success=True, data=moods or {})
    except Exception as exc:
        logger.error("ytmusic_moods error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/ytmusic/mood/playlists", tags=["YTMusic"])
@limiter.limit("10/second")
async def ytmusic_mood_playlists(
    request: Request,
    params: str = Query(..., description="Mood params string from /ytmusic/moods"),
):
    """Get playlists for a specific mood/genre."""
    global _cache_hits, _cache_misses
    cache_key = f"mood_playlists:{params}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        playlists = await asyncio.to_thread(ytmusic.get_mood_playlists, params)
        _search_cache[cache_key] = playlists or []
        return APIResponse(success=True, data=playlists or [])
    except Exception as exc:
        logger.error("mood_playlists error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 16. WATCH PLAYLIST (radio/auto-play)
# ---------------------------------------------------------------------------

@app.get("/ytmusic/watch_playlist", tags=["YTMusic"])
@limiter.limit("10/second")
async def ytmusic_watch_playlist(
    request: Request,
    videoId: str = Query(..., min_length=5),
    limit: int = Query(25, ge=1, le=50),
):
    """Get a YouTube Music radio/watch playlist for continuous playback."""
    global _cache_hits, _cache_misses
    cache_key = f"watch_playlist:{videoId}:{limit}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    try:
        watch_pl = await asyncio.to_thread(ytmusic.get_watch_playlist, videoId=videoId, limit=limit)
        tracks = (watch_pl or {}).get("tracks") or []
        result = {
            "tracks": [_map_ytmusic_result(t).model_dump() for t in tracks[:limit]],
            "lyrics": (watch_pl or {}).get("lyrics"),
            "related": (watch_pl or {}).get("related"),
        }
        _info_cache[cache_key] = result
        return APIResponse(success=True, data=result)
    except Exception as exc:
        logger.error("watch_playlist error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 17. SONG DETAILS (via ytmusicapi)
# ---------------------------------------------------------------------------

@app.get("/song/info", tags=["Song"])
@limiter.limit("10/second")
async def song_info(
    request: Request,
    videoId: str = Query(..., min_length=5),
):
    """Get rich song details from ytmusicapi (album, artist, category, etc.)."""
    global _cache_hits, _cache_misses
    cache_key = f"song_info:{videoId}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    try:
        details = await asyncio.to_thread(ytmusic.get_song, videoId)
        _info_cache[cache_key] = details or {}
        return APIResponse(success=True, data=details or {})
    except Exception as exc:
        logger.error("song_info error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 18. ALBUM BROWSE ID
# ---------------------------------------------------------------------------

@app.get("/album/browse", tags=["Album"])
@limiter.limit("10/second")
async def album_browse(
    request: Request,
    browseId: str = Query(..., min_length=5),
):
    """Get album details using its YouTube Music browseId."""
    global _cache_hits, _cache_misses
    cache_key = f"album_browse:{browseId}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    try:
        album = await asyncio.to_thread(ytmusic.get_album_browse_id, browseId)
        _info_cache[cache_key] = album or {}
        return APIResponse(success=True, data=album or {})
    except Exception as exc:
        logger.error("album_browse error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 19. ARTIST ALBUMS
# ---------------------------------------------------------------------------

@app.get("/artist/albums", tags=["Artist"])
@limiter.limit("10/second")
async def artist_albums(
    request: Request,
    browseId: str = Query(..., min_length=5),
    params: str = Query(..., description="'params' field from artist.albums section"),
):
    """Get all albums for an artist."""
    global _cache_hits, _cache_misses
    cache_key = f"artist_albums:{browseId}:{params}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    try:
        albums = await asyncio.to_thread(ytmusic.get_artist_albums, browseId, params)
        _info_cache[cache_key] = albums or []
        return APIResponse(success=True, data=albums or [])
    except Exception as exc:
        logger.error("artist_albums error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 20. USER PLAYLISTS (public)
# ---------------------------------------------------------------------------

@app.get("/user/playlists", tags=["Playlist"])
@limiter.limit("10/second")
async def user_playlists(
    request: Request,
    channelId: str = Query(..., min_length=5),
    params: str = Query(..., description="'params' field from user profile"),
):
    """Get public playlists for a YouTube user/channel."""
    global _cache_hits, _cache_misses
    cache_key = f"user_playlists:{channelId}:{params}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    try:
        playlists = await asyncio.to_thread(ytmusic.get_user_playlists, channelId, params)
        _info_cache[cache_key] = playlists or []
        return APIResponse(success=True, data=playlists or [])
    except Exception as exc:
        logger.error("user_playlists error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 21. TASTEPROFILE
# ---------------------------------------------------------------------------

@app.get("/ytmusic/tasteprofile", tags=["YTMusic"])
@limiter.limit("10/second")
async def ytmusic_tasteprofile(request: Request):
    """Get YouTube Music taste profile items (genres/moods to select)."""
    global _cache_hits, _cache_misses
    cache_key = "tasteprofile"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    try:
        profile = await asyncio.to_thread(ytmusic.get_tasteprofile)
        _search_cache[cache_key] = profile or {}
        return APIResponse(success=True, data=profile or {})
    except Exception as exc:
        logger.error("tasteprofile error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 22. YT-DLP FALLBACK SEARCH
# ---------------------------------------------------------------------------

@app.get("/yt/search", tags=["YouTube"])
@limiter.limit("10/second")
async def yt_search(
    request: Request,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
):
    """Search YouTube directly via yt-dlp (fallback when ytmusicapi fails)."""
    global _cache_hits, _cache_misses
    cache_key = f"yt_search:{q}:{limit}"
    if cache_key in _search_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_search_cache[cache_key])
    _cache_misses += 1
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
    }
    try:
        info = await _run_ydl(opts, f"ytsearch{limit}:{q}")
        entries = info.get("entries") or []
        results = []
        for e in entries:
            vid = e.get("id") or ""
            results.append({
                "videoId": vid,
                "title": e.get("title"),
                "artist": e.get("uploader") or e.get("channel"),
                "duration": _duration_str(e.get("duration")),
                "duration_seconds": e.get("duration"),
                "thumbnail": _thumb(vid) if vid else "",
                "url": _yt_url(vid) if vid else "",
                "isLive": e.get("is_live", False),
                "views": str(e.get("view_count", "N/A")),
            })
        _search_cache[cache_key] = results
        return APIResponse(success=True, data=results)
    except Exception as exc:
        logger.error("yt_search error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 23. VIDEO URL INFO (full yt-dlp metadata)
# ---------------------------------------------------------------------------

@app.get("/yt/info", tags=["YouTube"])
@limiter.limit("10/second")
async def yt_info(
    request: Request,
    url: str = Query(..., description="Full YouTube URL"),
):
    """Get complete yt-dlp metadata for any YouTube URL."""
    global _cache_hits, _cache_misses
    cache_key = f"yt_info:{url}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        info = await _run_ydl(opts, url)
        # Limit response size
        data = {
            "id": info.get("id"),
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "channel": info.get("channel"),
            "duration": info.get("duration"),
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
            "upload_date": info.get("upload_date"),
            "description": (info.get("description") or "")[:500],
            "thumbnail": info.get("thumbnail"),
            "webpage_url": info.get("webpage_url"),
            "is_live": info.get("is_live"),
            "categories": info.get("categories"),
            "tags": (info.get("tags") or [])[:20],
        }
        _info_cache[cache_key] = data
        return APIResponse(success=True, data=data)
    except Exception as exc:
        logger.error("yt_info error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 24. FORMATS LIST
# ---------------------------------------------------------------------------

@app.get("/video/formats", tags=["Video"])
@limiter.limit("10/second")
async def video_formats(
    request: Request,
    videoId: str = Query(..., min_length=5),
):
    """List all available download formats for a video."""
    global _cache_hits, _cache_misses
    cache_key = f"formats:{videoId}"
    if cache_key in _info_cache:
        _cache_hits += 1
        return APIResponse(success=True, data=_info_cache[cache_key])
    _cache_misses += 1
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        info = await _run_ydl(opts, _yt_url(videoId))
        formats = []
        for f in (info.get("formats") or []):
            formats.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "resolution": f.get("resolution"),
                "fps": f.get("fps"),
                "vcodec": f.get("vcodec"),
                "acodec": f.get("acodec"),
                "filesize": f.get("filesize"),
                "tbr": f.get("tbr"),
                "abr": f.get("abr"),
                "vbr": f.get("vbr"),
                "height": f.get("height"),
                "width": f.get("width"),
            })
        _info_cache[cache_key] = formats
        return APIResponse(success=True, data=formats)
    except Exception as exc:
        logger.error("video_formats error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL,
        reload=False,
    )
