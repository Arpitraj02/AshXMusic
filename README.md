# AshXMusic API 🎵

A **comprehensive, no-authentication-required** YouTube Music API built with **FastAPI**, **yt-dlp**, and **ytmusicapi**. Designed as a backend for Telegram music bots. No API keys, no OAuth, no paid services.

---

## ✨ Features

- **30+ REST endpoints** – Search, stream, download, metadata, playlists, artists, charts, and more.
- **No API keys** – Uses open-source unofficial libraries only.
- **Streaming support** – Direct audio/video stream URLs (Range requests supported).
- **In-memory caching** – TTL-based caching to reduce load.
- **Rate limiting** – 10 requests/second per IP.
- **CORS enabled** – `*` origins for Telegram bot flexibility.
- **Auto-docs** – Swagger UI at `/docs`.
- **Docker ready** – Includes `Dockerfile`.

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/Arpitraj02/AshXMusic.git
cd AshXMusic
pip install -r requirements.txt
```

### 2. Configure (optional)

```bash
cp .env.example .env
# Edit .env to customize HOST, PORT, LOG_LEVEL
```

### 3. Run

```bash
python main.py
```

The API will be available at `http://localhost:8000`.

Open **Swagger UI**: `http://localhost:8000/docs`

---

## 🐳 Docker

```bash
docker build -t ashxmusic .
docker run -p 8000:8000 ashxmusic
```

Or with environment variables:

```bash
docker run -p 8000:8000 -e PORT=8000 -e LOG_LEVEL=info ashxmusic
```

---

## 📋 API Endpoints

### Health & Stats
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/stats` | Uptime, cache stats |

### Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/search` | Search songs/videos/playlists/artists/albums |
| GET | `/search/suggestions` | Autocomplete suggestions |
| GET | `/search/related` | Related search queries |
| GET | `/search/trending` | Trending songs by category |
| GET | `/search/charts` | YouTube Music charts by country |
| POST | `/search/advanced` | Advanced search with filters |

### Video
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/video/info` | Rich video/song metadata |
| GET | `/video/thumbnail` | Redirect to thumbnail URL |
| GET | `/video/lyrics` | Song lyrics (if available) |
| GET | `/video/stream` | Direct video stream URL redirect |
| GET | `/video/formats` | List all available formats |

### Audio
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/audio/stream` | Direct audio stream URL redirect |
| GET | `/audio/download` | Stream audio bytes to client |
| GET | `/audio/info` | Audio stream URL + metadata (no redirect) |
| POST | `/batch/stream` | Get stream URLs for multiple videos |

### Artist
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/artist/info` | Artist top songs, albums, bio |
| GET | `/artist/albums` | All albums for an artist |
| GET | `/top/artists` | Top artists by country |

### Playlist
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/playlist/info` | Playlist details and tracks |
| GET | `/user/playlists` | Public playlists for a user/channel |

### Album
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/album/info` | Album details and tracks |
| GET | `/album/browse` | Album details by browseId |

### Song
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/song/info` | Rich song details from ytmusicapi |

### YouTube Music (ytmusicapi)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/ytmusic/search` | YTMusic search (all types) |
| GET | `/ytmusic/home` | Home feed (shelves, charts) |
| GET | `/ytmusic/library` | Simulated library |
| GET | `/ytmusic/browse` | Browse by browseId |
| GET | `/ytmusic/get_search_suggestions` | YTMusic-specific suggestions |
| GET | `/ytmusic/moods` | Mood/genre categories |
| GET | `/ytmusic/mood/playlists` | Playlists for a mood |
| GET | `/ytmusic/watch_playlist` | Radio/watch playlist for playback |
| GET | `/ytmusic/tasteprofile` | Taste profile items |

### Related
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/related/videos` | Recommended/related videos |

### Utility
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/random/song` | Random popular song by genre |
| GET | `/genre/browse` | Browse songs by genre |
| GET | `/live/streams` | Live music streams |

### YouTube (yt-dlp fallback)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/yt/search` | YouTube search via yt-dlp |
| GET | `/yt/info` | Full yt-dlp metadata for a URL |

---

## 📖 Example Requests

### Search for songs
```bash
curl "http://localhost:8000/search?q=taylor+swift&type=song&limit=10"
```

### Get audio stream URL
```bash
curl "http://localhost:8000/audio/stream?videoId=dQw4w9WgXcQ&format=best"
# → 302 redirect to direct audio URL
```

### Get audio info (no redirect)
```bash
curl "http://localhost:8000/audio/info?videoId=dQw4w9WgXcQ"
```

### Get video info
```bash
curl "http://localhost:8000/video/info?videoId=dQw4w9WgXcQ"
```

### Get search suggestions
```bash
curl "http://localhost:8000/search/suggestions?q=taylor&limit=5"
```

### Get YouTube Music charts
```bash
curl "http://localhost:8000/search/charts?country=US&limit=20"
```

### Get lyrics
```bash
curl "http://localhost:8000/video/lyrics?videoId=dQw4w9WgXcQ"
```

### Batch stream URLs
```bash
curl -X POST "http://localhost:8000/batch/stream" \
  -H "Content-Type: application/json" \
  -d '{"videoIds": ["dQw4w9WgXcQ", "9bZkp7q19f0"]}'
```

### Advanced search
```bash
curl -X POST "http://localhost:8000/search/advanced" \
  -H "Content-Type: application/json" \
  -d '{"query": "chill music", "filters": {"duration": "long", "type": "song"}, "limit": 10}'
```

### Random song
```bash
curl "http://localhost:8000/random/song?genre=pop"
```

### Get artist info
```bash
curl "http://localhost:8000/artist/info?browseId=UCVhQ2LWhmc7eu8LKDaFd30Q&limit=10"
```

---

## 📦 Response Format

Every endpoint returns:

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

On failure:

```json
{
  "success": false,
  "data": null,
  "error": "Error description"
}
```

---

## ⚙️ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `info` | Logging level (debug/info/warning/error) |

---

## 📦 Dependencies

- [FastAPI](https://fastapi.tiangolo.com/) – Web framework
- [uvicorn](https://www.uvicorn.org/) – ASGI server
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) – YouTube downloader/extractor
- [ytmusicapi](https://ytmusicapi.readthedocs.io/) – YouTube Music unofficial API
- [cachetools](https://github.com/tkem/cachetools/) – In-memory TTL caching
- [slowapi](https://github.com/laurentS/slowapi) – Rate limiting for FastAPI
- [pydantic](https://docs.pydantic.dev/) – Data validation/schemas
- [httpx](https://www.python-httpx.org/) – Async HTTP client (for proxy streaming)
- [python-dotenv](https://github.com/theskumar/python-dotenv) – `.env` file support

---

## 📝 Notes

- All endpoints are **async** and run yt-dlp in threads to avoid blocking.
- **ffmpeg** is required for audio remuxing (install separately or use the Docker image).
- Stream URLs from yt-dlp are typically short-lived (expire after a few hours); cache TTL is set accordingly.
- The `/audio/stream` and `/video/stream` endpoints return `302` redirects to direct CDN URLs for best performance with Telegram bots.
- For Telegram bots, use `/audio/info` to get the URL first, then send it directly.

---

## 🔒 License

Open-source, provided as-is. Uses unofficial APIs – use responsibly.
