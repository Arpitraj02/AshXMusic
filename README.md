# AshXMusic API 🎵

A **comprehensive, no-authentication-required** YouTube Music API built with **FastAPI**, **yt-dlp**, and **ytmusicapi**. Designed as a backend for Telegram music bots. No API keys, no OAuth, no paid services.

> **Live demo:** `https://ashxmusic.onrender.com`  
> **Swagger UI:** `https://ashxmusic.onrender.com/docs`

---

## ✨ Features

- **35+ REST endpoints** – Search, stream, download, metadata, playlists, artists, charts, recommendations, and more.
- **No API keys** – Uses open-source unofficial libraries only.
- **Cookie support** – Drop in a `cookies.txt` to bypass YouTube bot-detection.
- **Streaming support** – Direct audio/video stream URLs (Range requests supported).
- **Region-based recommendations** – India, US, UK, Pakistan, K-Pop, and more.
- **Stream & download URLs in search results** – Every search result includes ready-to-use `stream_url` and `download_url` fields.
- **In-memory caching** – TTL-based caching to reduce load.
- **Rate limiting** – 10 requests/second per IP.
- **CORS enabled** – `*` origins for Telegram bot flexibility.
- **Auto-docs** – Swagger UI at `/docs`, ReDoc at `/redoc`.
- **Docker ready** – Includes `Dockerfile`.

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/Arpitraj02/AshXMusic.git
cd AshXMusic
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env to set HOST, PORT, LOG_LEVEL, COOKIES_FILE, BASE_URL
```

### 3. (Optional but recommended) Add Cookies

YouTube increasingly requires authentication for stream extraction. Drop in a `cookies.txt` file – see [🍪 Cookies Setup Guide](#-cookies-setup-guide) below.

### 4. Run

```bash
python main.py
```

API available at `http://localhost:8000` · Swagger UI: `http://localhost:8000/docs`

---

## 🐳 Docker

```bash
docker build -t ashxmusic .
docker run -p 8000:8000 \
  -e BASE_URL=https://ashxmusic.onrender.com \
  -e COOKIES_FILE=/app/cookies.txt \
  -v /path/to/your/cookies.txt:/app/cookies.txt \
  ashxmusic
```

---

## 🍪 Cookies Setup Guide

YouTube may return the error:

```
Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies for authentication.
```

The fix is to export your YouTube session cookies and provide them to yt-dlp.

---

### Method 1 – Browser Extension (Desktop)

1. Install the **[Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)** extension in Chrome/Edge, or **[cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)** in Firefox.
2. Log in to [YouTube](https://www.youtube.com) / [YouTube Music](https://music.youtube.com) in that browser.
3. Click the extension icon → **Export** → save as `cookies.txt`.
4. Place `cookies.txt` in your project root (same directory as `main.py`).
5. Make sure your `.env` has `COOKIES_FILE=cookies.txt`.

---

### Method 2 – Kiwi Browser (Android / Mobile) 🤖

Kiwi Browser supports Chrome desktop extensions on Android, making it ideal for mobile cookie extraction.

**Step 1 – Install Kiwi Browser**  
Download from the [Google Play Store](https://play.google.com/store/apps/details?id=com.kiwibrowser.browser).

**Step 2 – Add the cookies extension**  
1. Open Kiwi Browser and go to `chrome://extensions`.
2. Enable **Developer mode** (toggle in the top right).
3. Tap **"+ (from store)"** and search for **"Get cookies.txt LOCALLY"** → Install.

**Step 3 – Export cookies**  
1. Visit [https://music.youtube.com](https://music.youtube.com) and log in with your Google account.
2. Tap the extension icon (puzzle-piece icon in the address bar) → **Get cookies.txt LOCALLY** → **Export**.
3. Choose **"Current site"** or **"music.youtube.com"** – this exports only YouTube cookies.
4. Save the file as `cookies.txt`.

**Step 4 – Transfer to server**  
Transfer `cookies.txt` to your server using:
- `scp cookies.txt user@server:/path/to/AshXMusic/cookies.txt`
- Or use the **[/cookies/upload](#cookiesupload)** API endpoint.

---

### Method 3 – Upload via API

If `COOKIES_ADMIN_TOKEN` is set in your `.env`, you can upload a new cookies file at runtime:

```bash
curl -X POST "https://ashxmusic.onrender.com/cookies/upload?token=YOUR_SECRET_TOKEN" \
  -F "file=@cookies.txt"
```

---

### Where to Place the cookies.txt File

| Scenario | Path |
|----------|------|
| Local / bare-metal | Project root → `AshXMusic/cookies.txt` |
| Docker | Mount as `/app/cookies.txt` and set `COOKIES_FILE=/app/cookies.txt` |
| Render.com | Use the upload API endpoint or mount a persistent disk at `/data/cookies.txt` |

**⚠️ Important:** `cookies.txt` is listed in `.gitignore`. **Never commit it to version control** – it contains your session tokens.

---

### Verifying Cookies are Loaded

```bash
curl https://ashxmusic.onrender.com/cookies/status
```

Response:
```json
{
  "success": true,
  "data": {
    "cookies_loaded": true,
    "cookies_file": "cookies.txt",
    "file_size_bytes": 4096,
    "note": "Cookies are active – yt-dlp will authenticate with YouTube."
  }
}
```

---

## ⚙️ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `info` | Logging level (debug/info/warning/error) |
| `COOKIES_FILE` | `cookies.txt` | Path to Netscape-format cookies file |
| `BASE_URL` | _(empty)_ | Your deployed API URL (e.g. `https://ashxmusic.onrender.com`). Used to build absolute `stream_url` / `download_url` in search results. |
| `COOKIES_ADMIN_TOKEN` | _(empty)_ | Secret token to protect `POST /cookies/upload`. Leave blank to disable. |

---

## 📋 API Endpoints

Base URL: `https://ashxmusic.onrender.com`

### Health & Stats
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/stats` | Uptime, cache stats |

### Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/search` | Search songs/videos/playlists/artists/albums (includes `stream_url` & `download_url`) |
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
| GET | `/audio/stream` | Direct audio stream URL redirect (302) |
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

### Recommendations (NEW)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/recommendations` | Region-based music recommendations (India default) |
| GET | `/recommendations/regions` | List all available regions and categories |

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

### Cookies (NEW)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cookies/status` | Check if cookies are loaded |
| POST | `/cookies/upload` | Upload a new cookies.txt file (requires `COOKIES_ADMIN_TOKEN`) |

---

## 📖 Example Requests

### Search for songs (with stream URLs)
```bash
curl "https://ashxmusic.onrender.com/search?q=arijit+singh&type=song&limit=5"
```
```json
{
  "success": true,
  "data": [
    {
      "videoId": "abc123",
      "title": "Tum Hi Ho",
      "artist": "Arijit Singh",
      "album": "Aashiqui 2",
      "duration": "4:22",
      "duration_seconds": 262,
      "thumbnail": "https://i.ytimg.com/vi/abc123/sddefault.jpg",
      "url": "https://www.youtube.com/watch?v=abc123",
      "stream_url": "https://ashxmusic.onrender.com/audio/stream?videoId=abc123",
      "download_url": "https://ashxmusic.onrender.com/audio/download?videoId=abc123",
      "isLive": false,
      "views": "1.2B",
      "explicit": false,
      "resultType": "song"
    }
  ],
  "error": null,
  "total": 1
}
```

### India Bollywood recommendations
```bash
curl "https://ashxmusic.onrender.com/recommendations?region=in&category=bollywood&limit=10"
```

### India Punjabi recommendations
```bash
curl "https://ashxmusic.onrender.com/recommendations?region=in&category=punjabi&limit=10"
```

### List all regions & categories
```bash
curl "https://ashxmusic.onrender.com/recommendations/regions"
```
```json
{
  "success": true,
  "data": {
    "in": { "name": "India", "categories": ["bollywood", "trending", "punjabi", "tamil", "telugu", "devotional"] },
    "us": { "name": "United States", "categories": ["pop", "hiphop", "country", "rnb"] },
    "gb": { "name": "United Kingdom", "categories": ["pop", "grime", "indie"] },
    "pk": { "name": "Pakistan", "categories": ["trending", "coke_studio", "urdu"] },
    "kp": { "name": "K-Pop / Korea", "categories": ["kpop", "trending"] }
  }
}
```

### Get audio stream URL
```bash
curl -L "https://ashxmusic.onrender.com/audio/stream?videoId=dQw4w9WgXcQ"
# → 302 redirect to direct CDN audio URL
```

### Get audio info (no redirect)
```bash
curl "https://ashxmusic.onrender.com/audio/info?videoId=dQw4w9WgXcQ"
```

### Check cookies status
```bash
curl "https://ashxmusic.onrender.com/cookies/status"
```

### Upload cookies file
```bash
curl -X POST "https://ashxmusic.onrender.com/cookies/upload?token=YOUR_SECRET" \
  -F "file=@/path/to/cookies.txt"
```

### Get YouTube Music charts for India
```bash
curl "https://ashxmusic.onrender.com/search/charts?country=IN&limit=20"
```

### Get lyrics
```bash
curl "https://ashxmusic.onrender.com/video/lyrics?videoId=dQw4w9WgXcQ"
```

### Batch stream URLs
```bash
curl -X POST "https://ashxmusic.onrender.com/batch/stream" \
  -H "Content-Type: application/json" \
  -d '{"videoIds": ["dQw4w9WgXcQ", "9bZkp7q19f0"]}'
```

---

## 📦 Response Format

Every endpoint returns:

```json
{
  "success": true,
  "data": { "..." },
  "error": null
}
```

On failure:

```json
{
  "success": false,
  "data": null,
  "error": "Descriptive error message"
}
```

---

## 📦 Dependencies

- [FastAPI](https://fastapi.tiangolo.com/) – Web framework
- [uvicorn](https://www.uvicorn.org/) – ASGI server
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) – YouTube downloader/extractor
- [ytmusicapi](https://ytmusicapi.readthedocs.io/) – YouTube Music unofficial API
- [cachetools](https://github.com/tkem/cachetools/) – In-memory TTL caching
- [slowapi](https://github.com/laurentS/slowapi) – Rate limiting for FastAPI
- [pydantic](https://docs.pydantic.dev/) – Data validation/schemas
- [httpx](https://www.python-httpx.org/) – Async HTTP client
- [python-dotenv](https://github.com/theskumar/python-dotenv) – `.env` file support

---

## 📝 Notes

- All endpoints are **async** and run yt-dlp in threads to avoid blocking.
- **ffmpeg** is required for audio remuxing (installed automatically in Docker).
- Stream URLs from yt-dlp are typically short-lived (expire after a few hours); cache TTL is set accordingly (120 s for streams).
- The `/audio/stream` and `/video/stream` endpoints return `302` redirects to direct CDN URLs for best performance with Telegram bots.
- For Telegram bots, use `/audio/info` to get the URL first, then pass it directly to the Telegram Bot API.
- If you get "Sign in to confirm you're not a bot" errors, upload a `cookies.txt` file – see the [Cookies Setup Guide](#-cookies-setup-guide).

---

## 🔒 Security

- `cookies.txt` is listed in `.gitignore` and **must never be committed**.
- The `/cookies/upload` endpoint is protected by `COOKIES_ADMIN_TOKEN` and is disabled by default.
- Rate limiting is enforced per IP (10 req/s, 5 req/s for batch).

---

## 🔒 License

Open-source, provided as-is. Uses unofficial APIs – use responsibly.
