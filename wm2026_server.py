#!/usr/bin/env python3
"""WM2026 Server (Windows / Lively Wallpaper).

Brings the macOS Uebersicht widget feature set to Windows:
- live ESPN scoreboard + schedule cache
- stream probing + mpv playback
- German TTS goal commentary via engine.py
- kicker + ESPN side-panel data
- optional desktop icon shift using the Windows shell folder view API
- helper endpoints for the Lively web widget
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from ctypes import wintypes
from flask import Flask, Response, jsonify, request, send_file


BASE_DIR = Path(os.environ.get("APPDATA", Path.home())) / "wm2026"
BASE_DIR.mkdir(parents=True, exist_ok=True)

SOURCES_PATH = BASE_DIR / "sources.json"
STREAMS_PATH = BASE_DIR / "streams.json"
AUDIO_STATE_PATH = BASE_DIR / "audio_state.json"
TICKER_PATH = BASE_DIR / "ticker.json"
COMMENTS_PATH = BASE_DIR / "comments.json"
COMMENTARY_PATH = BASE_DIR / "commentary.json"
STATE_PATH = BASE_DIR / "state.json"
FEED_PATH = BASE_DIR / "feed.json"
TODAY_PATH = BASE_DIR / "today.json"
SCHEDULE_PATH = BASE_DIR / "schedule.json"
AUDIO_ON_PATH = BASE_DIR / "audio_on"
SHIFT_STATE_PATH = BASE_DIR / "desktop_shift_state.json"
SHIFT_CONFIG_PATH = BASE_DIR / "shift_config.json"
ENGINE_PATH = BASE_DIR / "engine.py"

SERVER_PORT = 9876
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"
MAGENTA_URL = "https://web.magentatv.de"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
    except Exception:
        pass


def set_flag(path: Path, enabled: bool) -> None:
    if enabled:
        path.touch(exist_ok=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def file_uri(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return Path(path).resolve().as_uri()
    except Exception:
        return None


def get_wallpaper_path() -> str | None:
    SPI_GETDESKWALLPAPER = 0x0073
    buffer = ctypes.create_unicode_buffer(260)
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_GETDESKWALLPAPER, len(buffer), buffer, 0
    )
    if ok and buffer.value:
        return buffer.value
    return None


# ---------------------------------------------------------------------------
# mpv helpers
# ---------------------------------------------------------------------------

_mpv_lock = threading.RLock()
_mpv_process = None
_requested_url = None
_current_volume = 70
MPV_PIPE = r"\\.\pipe\mpv-wm2026"


def _find_mpv() -> str:
    candidates = [
        r"C:\Program Files\mpv\mpv.exe",
        r"C:\Program Files (x86)\mpv\mpv.exe",
        r"C:\Program Files\MPV Player\mpv.exe",
        r"C:\Program Files\mpv.net\mpvnet.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "mpv", "mpv.exe"),
        os.path.join(os.environ.get("USERPROFILE", ""), "scoop", "apps", "mpv", "current", "mpv.exe"),
        os.path.join(os.environ.get("USERPROFILE", ""), "scoop", "shims", "mpv.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return shutil.which("mpv") or "mpv"


MPV_BIN = _find_mpv()


def resolve_hls_audio(url: str, timeout: int = 6) -> str:
    if ".m3u8" not in url.lower():
        return url
    try:
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    except Exception:
        return url

    text = response.text
    if "#EXT-X-STREAM-INF" not in text and "#EXT-X-MEDIA" not in text:
        return url

    def is_good(candidate_url: str) -> bool:
        return "-b/" not in candidate_url and "-b." not in candidate_url

    audio_default = re.findall(
        r'#EXT-X-MEDIA:TYPE=AUDIO[^\n]*?DEFAULT=YES[^\n]*?URI="([^"]+)"',
        text,
    )
    audio_any = re.findall(r'#EXT-X-MEDIA:TYPE=AUDIO[^\n]*?URI="([^"]+)"', text)
    for candidate in audio_default + audio_any:
        full = urljoin(url, candidate)
        if is_good(full):
            return full

    variants = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF"):
            continue
        match = re.search(r"BANDWIDTH=(\d+)", line)
        bandwidth = int(match.group(1)) if match else 0
        for follow in range(index + 1, len(lines)):
            candidate = lines[follow].strip()
            if candidate and not candidate.startswith("#"):
                variants.append((bandwidth, urljoin(url, candidate)))
                break

    usable = [(bandwidth, candidate) for bandwidth, candidate in variants if is_good(candidate)]
    pool = usable or variants
    if pool:
        pool.sort(key=lambda entry: entry[0])
        return pool[0][1]
    return url


def mpv_is_running() -> bool:
    global _mpv_process
    return _mpv_process is not None and _mpv_process.poll() is None


def _send_pipe_command(cmd_list):
    try:
        with open(MPV_PIPE, "r+b", buffering=0) as pipe:
            payload = (json.dumps({"command": cmd_list}) + "\n").encode("utf-8")
            pipe.write(payload)
            return json.loads(pipe.readline().decode("utf-8").strip())
    except Exception:
        return None


def mpv_start(url: str, volume: int = 70) -> bool:
    global _mpv_process, _requested_url, _current_volume
    with _mpv_lock:
        mpv_stop()
        time.sleep(0.3)
        play_url = resolve_hls_audio(url)
        cmd = [
            MPV_BIN,
            "--no-video",
            "--force-window=no",
            f"--input-ipc-server={MPV_PIPE}",
            f"--volume={volume}",
            "--cache=yes",
            "--cache-secs=10",
            play_url,
        ]
        try:
            _mpv_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return False
        _requested_url = url
        _current_volume = int(volume)
        time.sleep(1.2)
        return mpv_is_running()


def mpv_stop() -> None:
    global _mpv_process, _requested_url
    with _mpv_lock:
        _requested_url = None
        if _mpv_process is None:
            return
        try:
            _send_pipe_command(["quit"])
            time.sleep(0.3)
        except Exception:
            pass
        if _mpv_process.poll() is None:
            _mpv_process.terminate()
            try:
                _mpv_process.wait(timeout=3)
            except Exception:
                _mpv_process.kill()
        _mpv_process = None


def mpv_set_volume(level: int) -> int:
    global _current_volume
    level = max(0, min(100, int(level)))
    _current_volume = level
    _send_pipe_command(["set_property", "volume", level])
    return level


def mpv_get_status():
    if not mpv_is_running():
        return {"playing": False, "url": None, "volume": _current_volume}

    volume = _current_volume
    response = _send_pipe_command(["get_property", "volume"])
    if isinstance(response, dict) and response.get("data") is not None:
        try:
            volume = int(response["data"])
        except Exception:
            volume = _current_volume
    return {"playing": True, "url": _requested_url, "volume": volume}


# ---------------------------------------------------------------------------
# Windows desktop icon shift
# ---------------------------------------------------------------------------

_shift_lock = threading.RLock()


def _get_desktop_folder_view():
    try:
        import pythoncom
        import win32com.client as win32_client
        from win32com.shell import shell, shellcon
    except ImportError as exc:
        raise RuntimeError("pywin32 is required for desktop icon shifting") from exc

    clsid_shell_windows = "{9BA05972-F6A8-11CF-A442-00A0C90A8F39}"
    iid_folder_view = "{CDE725B0-CCC9-4519-917E-325D72FAB4CE}"
    swc_desktop = 0x08
    swfo_needdispatch = 0x01

    pythoncom.CoInitialize()
    shell_windows = win32_client.Dispatch(clsid_shell_windows)
    dispatch = shell_windows.FindWindowSW(
        win32_client.VARIANT(pythoncom.VT_I4, shellcon.CSIDL_DESKTOP),
        win32_client.VARIANT(pythoncom.VT_EMPTY, None),
        swc_desktop,
        0,
        swfo_needdispatch,
    )
    service_provider = dispatch._oleobj_.QueryInterface(pythoncom.IID_IServiceProvider)
    browser = service_provider.QueryService(shell.SID_STopLevelBrowser, shell.IID_IShellBrowser)
    shell_view = browser.QueryActiveShellView()
    folder_view = shell_view.QueryInterface(iid_folder_view)
    shell_folder = folder_view.GetFolder(shell.IID_IShellFolder)
    return pythoncom, shellcon, folder_view, shell_folder


def get_shift_positions(direction: str) -> dict[str, list[int]]:
    config = load_json(SHIFT_CONFIG_PATH, {"icons": {}})
    positions = {}
    for name, values in config.get("icons", {}).items():
        target = "open" if direction == "right" else "closed"
        coords = values.get(target)
        if (
            isinstance(coords, list)
            and len(coords) == 2
            and all(isinstance(value, (int, float)) for value in coords)
        ):
            positions[name] = [int(coords[0]), int(coords[1])]
    return positions


def shift_desktop_icons(direction: str):
    if direction not in {"left", "right"}:
        raise ValueError(f"unsupported direction: {direction}")

    positions = get_shift_positions(direction)
    if not positions:
        shifted = direction == "right"
        save_json(SHIFT_STATE_PATH, {"shifted": shifted})
        return {"ok": True, "shifted": shifted, "moved": 0, "missing": [], "note": "no shift_config.json"}

    with _shift_lock:
        pythoncom, shellcon, folder_view, shell_folder = _get_desktop_folder_view()
        moved = 0
        missing = []
        try:
            item_count = folder_view.ItemCount(shellcon.SVGIO_ALLVIEW)
            items_by_name = {}
            for index in range(item_count):
                item = folder_view.Item(index)
                name = shell_folder.GetDisplayNameOf(item, shellcon.SHGDN_NORMAL)
                items_by_name[name] = item

            for name, (x_pos, y_pos) in positions.items():
                item = items_by_name.get(name)
                if item is None:
                    missing.append(name)
                    continue
                folder_view.SelectAndPositionItem(item, (x_pos, y_pos), shellcon.SVSI_POSITIONITEM)
                moved += 1

            shifted = direction == "right"
            save_json(SHIFT_STATE_PATH, {"shifted": shifted})
            return {"ok": True, "shifted": shifted, "moved": moved, "missing": missing}
        finally:
            pythoncom.CoUninitialize()


# ---------------------------------------------------------------------------
# Streams
# ---------------------------------------------------------------------------

def check_stream_reachable(url: str, timeout: int = 3) -> bool:
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code < 400:
            return True
        response = requests.get(url, timeout=timeout, stream=True, allow_redirects=True)
        return response.status_code < 400
    except Exception:
        return False


def scrape_sportschau() -> list[str]:
    urls = []
    try:
        response = requests.get("https://www.sportschau.de/streams", timeout=8)
        response.raise_for_status()
        found = re.findall(r'https?://[^\s"\'<>]+\.m3u8', response.text)
        for url in found:
            if url not in urls:
                urls.append(url)
    except Exception:
        pass
    return urls


def find_streams():
    config = load_json(SOURCES_PATH, {"sources": []})
    tasks = []
    for source in config.get("sources", []):
        sid = source.get("id")
        name = source.get("name", sid)
        language = source.get("language", "?")
        country = source.get("country", "?")
        source_type = source.get("type", "static")
        if source_type == "static":
            url = source.get("url")
            if url:
                tasks.append((url, name, language, country, sid))
        elif source_type == "scrape" and sid == "ard-sportschau":
            for index, url in enumerate(scrape_sportschau()):
                display = f"{name} #{index + 1}" if index > 0 else name
                tasks.append((url, display, language, country, sid))

    results = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        future_map = {
            executor.submit(check_stream_reachable, url): (url, name, language, country, sid)
            for url, name, language, country, sid in tasks
        }
        for future in as_completed(future_map):
            url, name, language, country, sid = future_map[future]
            try:
                online = future.result()
            except Exception:
                online = False
            results.append(
                {
                    "id": sid,
                    "name": name,
                    "url": url,
                    "language": language,
                    "country": country,
                    "online": online,
                }
            )

    lang_order = {"de": 0, "en": 1}
    results.sort(key=lambda item: (0 if item["online"] else 1, lang_order.get(item["language"], 9), item["name"]))
    save_json(STREAMS_PATH, results)
    return results


def stream_finder_loop():
    while True:
        try:
            find_streams()
        except Exception:
            pass
        time.sleep(120)


# ---------------------------------------------------------------------------
# ESPN / commentary / comments
# ---------------------------------------------------------------------------

COMMENTS_ENABLED = True
_today_data = {"events": []}
_schedule_data = {"events": []}
_today_last = 0.0
_schedule_last = 0.0


def fetch_espn_today():
    try:
        today = datetime.utcnow().strftime("%Y%m%d")
        url = (
            "https://site.api.espn.com/apis/site/v2/sports/soccer/"
            f"fifa.world/scoreboard?dates={today}&limit=30"
        )
        response = requests.get(url, timeout=10, headers={"Accept": "application/json"})
        response.raise_for_status()
        return response.json()
    except Exception:
        return {"events": []}


def fetch_espn_schedule():
    try:
        url = (
            "https://site.api.espn.com/apis/site/v2/sports/soccer/"
            "fifa.world/scoreboard?dates=20260611-20260720&limit=120"
        )
        response = requests.get(url, timeout=20, headers={"Accept": "application/json"})
        response.raise_for_status()
        return response.json()
    except Exception:
        return {"events": []}


def fetch_espn_ticker():
    try:
        events = _today_data.get("events", [])
        ticker = []
        for event in events:
            competition = event.get("competitions", [{}])[0]
            status = competition.get("status", {})
            status_type = status.get("type", {})
            competitors = competition.get("competitors", [])
            home = next((item for item in competitors if item.get("homeAway") == "home"), competitors[0] if competitors else {})
            away = next(
                (item for item in competitors if item.get("homeAway") == "away"),
                competitors[1] if len(competitors) > 1 else {},
            )
            ticker.append(
                {
                    "id": event.get("id"),
                    "home": home.get("team", {}).get("shortDisplayName", "Heim"),
                    "away": away.get("team", {}).get("shortDisplayName", "Gast"),
                    "home_score": home.get("score", "0"),
                    "away_score": away.get("score", "0"),
                    "state": status_type.get("state", "pre"),
                    "clock": status.get("displayClock", ""),
                    "detail": status_type.get("shortDetail", ""),
                }
            )
        return ticker
    except Exception:
        return []


def fetch_espn_commentary():
    ticker = load_json(TICKER_PATH, [])
    live_games = [game for game in ticker if game.get("state") == "in"]
    all_events = []
    for game in live_games[:3]:
        game_id = game.get("id")
        if not game_id:
            continue
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={game_id}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            match_label = (
                f"{game.get('home', '')} {game.get('home_score', '0')}:"
                f"{game.get('away_score', '0')} {game.get('away', '')}"
            )
            for play in (data.get("plays") or data.get("commentary") or [])[-60:]:
                if not isinstance(play, dict):
                    continue
                clock_obj = play.get("clock", {})
                clock = clock_obj.get("displayValue", "") if isinstance(clock_obj, dict) else str(clock_obj or "")
                text = play.get("text") or play.get("description") or ""
                type_obj = play.get("type", {})
                event_type = (
                    (type_obj.get("text") or type_obj.get("id") or "")
                    if isinstance(type_obj, dict)
                    else str(type_obj or "")
                )
                if text:
                    all_events.append(
                        {
                            "match": match_label,
                            "clock": clock,
                            "type": event_type,
                            "text": text,
                            "game_id": game_id,
                        }
                    )

            for scoring_play in data.get("scoringPlays") or []:
                if not isinstance(scoring_play, dict):
                    continue
                clock_obj = scoring_play.get("clock", {})
                clock = clock_obj.get("displayValue", "") if isinstance(clock_obj, dict) else str(clock_obj or "")
                text = scoring_play.get("text") or scoring_play.get("description") or ""
                if text:
                    all_events.append(
                        {
                            "match": match_label,
                            "clock": clock,
                            "type": "goal",
                            "text": "⚽ " + text,
                            "game_id": game_id,
                        }
                    )
        except Exception:
            pass
    return all_events


def fetch_kicker_comments():
    if not COMMENTS_ENABLED:
        return []
    comments = []
    try:
        response = requests.get(
            "https://www.kicker.de/fifa-weltmeisterschaft-2026/spieltag",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for element in soup.find_all(["p", "div"]):
            text = element.get_text(strip=True)
            if 20 < len(text) < 300 and any(marker in text for marker in ["'", "Minute", "Tor", "Foul", "Ecke", "Abseits"]):
                comments.append({"time": "", "text": text, "source": "kicker"})
            if len(comments) >= 20:
                break
    except Exception:
        pass
    return comments


def data_fetch_loop():
    global _today_data, _schedule_data, _today_last, _schedule_last
    while True:
        try:
            now = time.time()
            if now - _today_last > 30:
                _today_data = fetch_espn_today()
                _today_last = now
                save_json(TODAY_PATH, _today_data)
                save_json(TICKER_PATH, fetch_espn_ticker())
            if now - _schedule_last > 600:
                _schedule_data = fetch_espn_schedule()
                _schedule_last = now
                save_json(SCHEDULE_PATH, _schedule_data)
        except Exception:
            pass
        time.sleep(5)


def comments_loop():
    while True:
        try:
            save_json(COMMENTS_PATH, fetch_kicker_comments())
        except Exception:
            pass
        time.sleep(45)


def commentary_loop():
    while True:
        try:
            ticker = load_json(TICKER_PATH, [])
            if any(game.get("state") == "in" for game in ticker):
                save_json(COMMENTARY_PATH, fetch_espn_commentary())
            else:
                save_json(COMMENTARY_PATH, [])
        except Exception:
            pass
        time.sleep(30)


def engine_loop():
    while True:
        try:
            if ENGINE_PATH.exists():
                subprocess.run(
                    [sys.executable, str(ENGINE_PATH)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=8,
                    check=False,
                )
        except Exception:
            pass
        time.sleep(3)


# ---------------------------------------------------------------------------
# Global mouse-wheel forwarding
# Lively does not forward wheel events to desktop wallpapers (issue #853), so
# we capture them with a low-level hook and expose the delta to the widget.
# ---------------------------------------------------------------------------

_wheel = {"total": 0}


def mouse_wheel_hook_loop():
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    WH_MOUSE_LL = 14
    WM_MOUSEWHEEL = 0x020A
    LRESULT = ctypes.c_ssize_t
    desktop_classes = {"SysListView32", "SHELLDLL_DefView", "WorkerW", "Progman"}

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("pt", POINT),
            ("mouseData", ctypes.c_uint),
            ("flags", ctypes.c_uint),
            ("time", ctypes.c_uint),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.WindowFromPoint.restype = ctypes.c_void_p
    user32.WindowFromPoint.argtypes = [POINT]
    user32.CallNextHookEx.restype = LRESULT
    user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

    def over_desktop(pt):
        hwnd = user32.WindowFromPoint(pt)
        if not hwnd:
            return False
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ctypes.c_void_p(hwnd), buf, 256)
        return buf.value in desktop_classes

    def proc(n_code, w_param, l_param):
        if n_code == 0 and w_param == WM_MOUSEWHEEL:
            info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if over_desktop(info.pt):
                _wheel["total"] += ctypes.c_short((info.mouseData >> 16) & 0xFFFF).value
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    callback = HOOKPROC(proc)
    user32.SetWindowsHookExW(WH_MOUSE_LL, callback, kernel32.GetModuleHandleW(None), 0)
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    return response


@app.route("/api/wheel_stream", methods=["GET"])
def api_wheel_stream():
    def gen():
        yield ": connected\n\n"
        last = _wheel["total"]
        ticks = 0
        while True:
            cur = _wheel["total"]
            if cur != last:
                diff = cur - last
                last = cur
                yield f"data: {diff}\n\n"
            else:
                ticks += 1
                if ticks >= 500:
                    ticks = 0
                    yield ": ping\n\n"
            time.sleep(0.02)
    return Response(gen(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.route("/api/status", methods=["GET"])
def api_status():
    shift_state = load_json(SHIFT_STATE_PATH, {"shifted": False})
    return jsonify(
        {
            "ok": True,
            "server": "wm2026-windows-lively",
            "audio": mpv_get_status(),
            "audio_on": AUDIO_ON_PATH.exists(),
            "shifted": bool(shift_state.get("shifted", False)),
            "wallpaper": file_uri(get_wallpaper_path()),
            "has_shift_config": SHIFT_CONFIG_PATH.exists(),
        }
    )


@app.route("/api/play", methods=["POST"])
def api_play():
    data = request.get_json(force=True) or {}
    url = data.get("url")
    volume = data.get("volume", _current_volume)
    if not url:
        return jsonify({"error": "url required"}), 400
    if not mpv_start(url, int(volume)):
        return jsonify({"error": "failed to start audio - is mpv installed?"}), 503
    state = mpv_get_status()
    save_json(AUDIO_STATE_PATH, state)
    return jsonify({"ok": True, "audio": state})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    mpv_stop()
    state = {"playing": False, "url": None, "volume": _current_volume}
    save_json(AUDIO_STATE_PATH, state)
    return jsonify({"ok": True, "audio": state})


@app.route("/api/volume", methods=["POST"])
def api_volume():
    data = request.get_json(force=True) or {}
    level = data.get("level")
    if level is None:
        return jsonify({"error": "level required"}), 400
    try:
        level = int(level)
    except (TypeError, ValueError):
        return jsonify({"error": "level must be a number"}), 400
    mpv_set_volume(level)
    state = mpv_get_status()
    save_json(AUDIO_STATE_PATH, state)
    return jsonify({"ok": True, "audio": state})


@app.route("/api/streams", methods=["GET"])
def api_streams():
    return jsonify({"streams": load_json(STREAMS_PATH, [])})


@app.route("/api/ticker", methods=["GET"])
def api_ticker():
    return jsonify({"ticker": load_json(TICKER_PATH, [])})


@app.route("/api/today", methods=["GET"])
def api_today():
    return jsonify(load_json(TODAY_PATH, _today_data))


@app.route("/api/schedule", methods=["GET"])
def api_schedule():
    return jsonify(load_json(SCHEDULE_PATH, _schedule_data))


@app.route("/api/feed", methods=["GET"])
def api_feed():
    return jsonify({"feed": load_json(FEED_PATH, [])})


@app.route("/api/comments", methods=["GET"])
def api_comments():
    return jsonify({"enabled": COMMENTS_ENABLED, "comments": load_json(COMMENTS_PATH, [])})


@app.route("/api/comments/toggle", methods=["POST"])
def api_comments_toggle():
    global COMMENTS_ENABLED
    data = request.get_json(force=True) or {}
    COMMENTS_ENABLED = bool(data.get("enabled", True))
    if not COMMENTS_ENABLED:
        save_json(COMMENTS_PATH, [])
    return jsonify({"enabled": COMMENTS_ENABLED})


@app.route("/api/commentary", methods=["GET"])
def api_commentary():
    return jsonify({"commentary": load_json(COMMENTARY_PATH, [])})


@app.route("/api/audio_on/toggle", methods=["POST"])
def api_audio_on_toggle():
    data = request.get_json(force=True) or {}
    enabled = bool(data.get("enabled", True))
    set_flag(AUDIO_ON_PATH, enabled)
    return jsonify({"audio_on": enabled})


@app.route("/api/test_audio", methods=["POST"])
def api_test_audio():
    try:
        subprocess.Popen(
            [sys.executable, str(ENGINE_PATH), "--speak-test"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True})


@app.route("/api/open_magentatv", methods=["POST"])
def api_open_magentatv():
    try:
        webbrowser.open(MAGENTA_URL, new=2)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "url": MAGENTA_URL})


@app.route("/api/shift", methods=["POST"])
def api_shift():
    data = request.get_json(force=True) or {}
    direction = data.get("dir", "right")
    try:
        result = shift_desktop_icons(direction)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"ok": False, "shifted": False, "error": str(exc)}), 500


@app.route("/api/wallpaper", methods=["GET"])
def api_wallpaper():
    path = get_wallpaper_path()
    return jsonify({"path": path, "uri": file_uri(path)})


@app.route("/api/wallpaper_image", methods=["GET"])
def api_wallpaper_image():
    path = get_wallpaper_path()
    if not path or not os.path.exists(path):
        return ("", 404)
    return send_file(path)


def ensure_default_state():
    if not SOURCES_PATH.exists():
        save_json(SOURCES_PATH, {"sources": []})
    if not AUDIO_STATE_PATH.exists():
        save_json(AUDIO_STATE_PATH, {"playing": False, "url": None, "volume": _current_volume})
    if not SHIFT_STATE_PATH.exists():
        save_json(SHIFT_STATE_PATH, {"shifted": False})


if __name__ == "__main__":
    ensure_default_state()
    print(f"WM2026 Windows server starting - data dir: {BASE_DIR}")
    print(f"mpv: {MPV_BIN}")
    for target in (stream_finder_loop, data_fetch_loop, comments_loop, commentary_loop, engine_loop, mouse_wheel_hook_loop):
        threading.Thread(target=target, daemon=True).start()
    print(f"Server listening on {SERVER_URL}")
    app.run(host="127.0.0.1", port=SERVER_PORT, debug=False, threaded=True)
