# ⚽ WM 2026 — Windows Desktop Widget

> A real-time FIFA World Cup 2026 sidebar widget for [Lively Wallpaper](https://livelywallpaper.app/) on Windows.
> Live scores · Full schedule · 20+ radio streams · German TTS commentary — all in one slick dark panel.

![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?logo=windows)
![Lively](https://img.shields.io/badge/Lively%20Wallpaper-widget-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-yellow?logo=python)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

| | |
|---|---|
| 🔴 **Live scores** | Updates every 3 seconds via the ESPN API |
| 📅 **Full schedule** | All 104 games grouped by day, with venues and round labels |
| 📻 **20+ radio streams** | ARD, ZDF, BBC, NPR and more — played via mpv |
| 🗣 **German TTS** | Windows `System.Speech` announces goals, kick-offs and final whistles |
| 📊 **Play-by-play** | ESPN event feed with goal / card / substitution highlights |
| 📺 **Live ticker panel** | Slide-out side panel with real-time scores for all live games |
| ⏳ **Countdown** | Days · Hours · Minutes until the tournament kicks off |
| 🖼 **Wallpaper background** | Automatically adopts the current Windows wallpaper for an overlay look |
| 🙈 **Hide / show** | Collapse the whole widget to a minimal notch — one click to restore |
| 🖥 **Responsive** | Adapts width for 1440p · 1920p · 2560p · 4K displays |
| ⚙️ **Configurable streams** | Add or swap radio sources in `sources.json` |
| 🖱 **Desktop icon shift** | Optionally moves Windows desktop icons aside when the ticker panel opens |

---

## Architecture

```
widget/ (Lively web widget)        ← index.html · app.js · styles.css
  │  fetch() every 3 s  →  wm2026_server.py  (Flask, port 9876)
  │
wm2026_server.py
  ├─ background loops
  │    ├─ data fetch    →  curl ESPN API → today.json / schedule.json / ticker.json
  │    ├─ engine.py     →  feed.json, state.json (goal detection + TTS)
  │    ├─ stream finder →  probes all sources every 2 min
  │    ├─ commentary    →  ESPN play-by-play (live games only)
  │    └─ comments      →  kicker.de live-ticker scrape (45 s)
  │
  └─ REST API
       ├─ /api/status        server + audio + wallpaper state
       ├─ /api/today         today's scoreboard (ESPN)
       ├─ /api/schedule      full tournament schedule (ESPN)
       ├─ /api/ticker        live scoreboard
       ├─ /api/feed          goal/event feed from engine.py
       ├─ /api/play|stop     start / stop a stream (mpv)
       ├─ /api/volume        adjust volume
       ├─ /api/streams       available / reachable streams
       ├─ /api/commentary    ESPN play-by-play
       ├─ /api/comments      kicker.de live-ticker snippets
       ├─ /api/wallpaper     current desktop wallpaper
       └─ /api/shift         move Windows desktop icons (optional)
```

Data files live in `%APPDATA%\wm2026\` and are **never** committed (see `.gitignore`).

---

## Requirements

| Tool | Notes |
|------|-------|
| **Windows 10 / 11** | Uses `System.Speech` (TTS), `winsound`, Windows Shell API |
| **[Lively Wallpaper](https://livelywallpaper.app/)** | Free animated/web wallpaper host |
| **Python 3.10+** | Installed via the official installer (provides the `py` launcher) |
| **[mpv](https://mpv.io)** | Audio playback — **automatically installed by `install.ps1`** (via winget) |

---

## Quick Start

```powershell
# 1. Clone
git clone https://github.com/AlexDesign420/wm2026-widget-windows.git
cd wm2026-widget-windows

# 2. Install (creates a venv in %APPDATA%\wm2026, installs deps)
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Then:

1. Open **Lively Wallpaper**.
2. Drag & drop the [`widget`](widget) folder into Lively to import it.
3. Run **`start_server.bat`** (or **`start_server_hidden.vbs`** for no console window).
4. Activate the wallpaper in Lively.

The widget connects to the local server automatically and shows an "offline" banner with start instructions until the server is running.

> **Scrolling the schedule:** Lively does not forward the mouse wheel to web wallpapers ([lively#853](https://github.com/rocksdanister/lively/issues/853)). Move the cursor to the **top or bottom edge** of the list to auto-scroll (faster the closer to the edge). This works purely via mouse-movement, which Lively does forward.

---

## Configuration

### Adding or changing streams

Edit `sources.json` (or `%APPDATA%\wm2026\sources.json` after install).
Each entry is either a `static` URL or a `scrape` target:

```jsonc
{
  "id": "my-station",
  "name": "My Radio",
  "country": "DE",
  "language": "de",
  "type": "static",
  "url": "https://example.com/stream.mp3"
}
```

The server checks all streams in parallel every 2 minutes and only shows reachable ones in the widget.

### Goal sound + TTS

Toggle "Tor-Sound" in the widget to enable/disable the `engine.py` commentary, and use **▶ Test** to verify audio output. TTS uses the first installed German Windows voice via `System.Speech`. Install additional voices under *Settings → Time & Language → Speech*.

### Desktop icon shift (optional)

When the ticker side-panel slides open, the server can move your Windows desktop icons to make room. To enable this:

```powershell
copy "$env:APPDATA\wm2026\shift_config.example.json" "$env:APPDATA\wm2026\shift_config.json"
```

Then edit `shift_config.json` — set the icon names and pixel positions to match **your** desktop layout. The feature is silently disabled if the file is missing.

> **Important:** Disable *Auto arrange icons* and *Align icons to grid* on the Windows desktop, otherwise Windows may reset the positions. This feature uses the Windows Shell folder-view API and requires `pywin32`.

---

## File Reference

| File | Purpose |
|------|---------|
| `widget/` | Lively web widget — import this folder into Lively |
| `wm2026_server.py` | Flask backend — runs on `127.0.0.1:9876` |
| `engine.py` | Detects goals/events, writes the feed, triggers TTS |
| `sources.json` | Radio/TV stream sources |
| `shift_config.example.json` | Template for the optional desktop icon shift feature |
| `install.ps1` | One-command installer (venv + dependencies) |
| `start_server.bat` | Starts the backend server |
| `start_server_hidden.vbs` | Starts the server without a console window |
| `requirements.txt` | Python dependencies |

---

## API Endpoints

The local server exposes a simple REST API (CORS enabled, localhost only):

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/status` | Server, audio and wallpaper state |
| `GET` | `/api/today` | Today's scoreboard (ESPN) |
| `GET` | `/api/schedule` | Full tournament schedule (ESPN) |
| `GET` | `/api/ticker` | Live scoreboard |
| `GET` | `/api/feed` | Goal/event feed from `engine.py` |
| `POST` | `/api/play` | `{"url": "...", "volume": 70}` — start stream |
| `POST` | `/api/stop` | Stop current stream |
| `POST` | `/api/volume` | `{"level": 70}` — adjust volume |
| `GET` | `/api/streams` | All stream sources with online status |
| `GET` | `/api/commentary` | Play-by-play events (live games only) |
| `GET` | `/api/comments` | kicker.de live ticker snippets |
| `POST` | `/api/comments/toggle` | Enable/disable comment scraping |
| `POST` | `/api/audio_on/toggle` | Enable/disable TTS commentary |
| `POST` | `/api/test_audio` | Play a TTS test announcement |
| `POST` | `/api/open_magentatv` | Open MagentaTV in the browser |
| `GET` | `/api/wallpaper` | Current desktop wallpaper path/URI |
| `GET` | `/api/wallpaper_image` | Current wallpaper served as an image |
| `POST` | `/api/shift` | `{"dir": "right" \| "left"}` — shift desktop icons |

---

## Data Sources

- **Scores & schedule** — [ESPN public API](https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard) — no API key required
- **Play-by-play** — ESPN summary endpoint
- **Live-ticker text** — kicker.de (scraped)
- **Streams** — Public broadcaster HLS/Icecast streams (ARD, ZDF, BBC, NPR, …)

---

## Troubleshooting

**Widget shows "Server offline"**
Start the backend: run `start_server.bat` or `start_server_hidden.vbs`. The widget retries every 3 seconds.

**Widget shows "Streams werden geprüft…"**
The server needs a moment to probe all streams on first launch. Wait ~10 seconds.

**No audio / "failed to start audio"**
mpv is installed automatically by `install.ps1`. If audio still fails, verify mpv is reachable (`mpv --version`); the server checks `PATH` and common install locations (Program Files\MPV Player, Scoop). Open a new terminal so an updated `PATH` takes effect.

**Can't scroll the schedule**
The mouse wheel is not forwarded to Lively web wallpapers. Move the cursor to the top/bottom edge of the list to auto-scroll.

**TTS says nothing**
Install a German voice under *Settings → Time & Language → Speech*. Use the **▶ Test** button to verify.

**Desktop icons don't move**
Install `pywin32` (handled by `install.ps1`) and disable *Auto arrange icons* / *Align icons to grid* on the desktop.

**Server doesn't start**
Start it manually to see errors:
```powershell
& "$env:APPDATA\wm2026\.venv\Scripts\python.exe" "$env:APPDATA\wm2026\wm2026_server.py"
```

---

## License

MIT — see [LICENSE](LICENSE).
