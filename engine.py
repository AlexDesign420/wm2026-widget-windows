#!/usr/bin/env python3
"""WM2026 Engine for Windows.

Reads today.json, compares it with the last known state and:
- writes feed.json for the widget
- speaks German goal / kickoff / final whistle commentary
- plays short Windows alert sounds
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import winsound
from pathlib import Path


DIR = Path(os.environ.get("APPDATA", Path.home())) / "wm2026"
AUDIO_ON_PATH = DIR / "audio_on"


def load(name: str, default):
    try:
        with (DIR / name).open(encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save(name: str, data) -> None:
    try:
        with (DIR / name).open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
    except Exception:
        pass


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def speak(text: str) -> None:
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$v = $s.GetInstalledVoices() | ForEach-Object {$_.VoiceInfo} | "
        "Where-Object { $_.Culture.Name -like 'de*' } | Select-Object -First 1; "
        "if ($v) { $s.SelectVoice($v.Name) }; "
        f"$s.Speak({_ps_quote(text)})"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def play(kind: str) -> None:
    try:
        if kind == "goal":
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        else:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


def run_engine() -> None:
    today = load("today.json", {"events": []})
    previous = load("state.json", {})
    feed = load("feed.json", [])

    audio_on = AUDIO_ON_PATH.exists()
    first_run = not previous

    new_state = {}
    spoken = []

    for event in today.get("events", []):
        try:
            competition = event["competitions"][0]
            status = competition["status"]["type"]["state"]
            clock = competition["status"].get("displayClock", "") or ""
            competitors = competition["competitors"]
            home = next((item for item in competitors if item.get("homeAway") == "home"), competitors[0])
            away = next((item for item in competitors if item.get("homeAway") == "away"), competitors[1])
            home_name = home["team"].get("shortDisplayName", "Heim")
            away_name = away["team"].get("shortDisplayName", "Gast")
            home_score = int(home.get("score", 0) or 0)
            away_score = int(away.get("score", 0) or 0)
            game_id = str(event.get("id"))
        except Exception:
            continue

        new_state[game_id] = {"h": home_score, "a": away_score, "state": status, "clock": clock}
        prev = previous.get(game_id)

        if first_run or prev is None:
            continue

        if status == "in" and prev.get("state") == "in":
            if home_score > prev.get("h", home_score):
                spoken.append(
                    (
                        "goal",
                        f"Tooor fuer {home_name}! Es steht jetzt {home_score} zu {away_score} gegen {away_name}.",
                    )
                )
                feed.insert(0, {"t": clock, "txt": f"TOR {home_name} - {home_score}:{away_score}", "kind": "goal"})
            if away_score > prev.get("a", away_score):
                spoken.append(
                    ("goal", f"Tooor fuer {away_name}! Es steht jetzt {home_score} zu {away_score}.")
                )
                feed.insert(0, {"t": clock, "txt": f"TOR {away_name} - {home_score}:{away_score}", "kind": "goal"})

        if prev.get("state") != status:
            if status == "in" and prev.get("state") == "pre":
                spoken.append(("whistle", f"Anpfiff! {home_name} gegen {away_name}."))
                feed.insert(0, {"t": clock or "1'", "txt": f"Anpfiff: {home_name} vs {away_name}", "kind": "start"})
            elif status == "post":
                result = "Unentschieden" if home_score == away_score else (
                    f"{home_name} gewinnt" if home_score > away_score else f"{away_name} gewinnt"
                )
                spoken.append(
                    (
                        "whistle",
                        f"Abpfiff. {home_name} {home_score}, {away_name} {away_score}. {result}.",
                    )
                )
                feed.insert(0, {"t": "FT", "txt": f"Ende: {home_name} {home_score}:{away_score} {away_name}", "kind": "end"})

    feed = feed[:40]
    save("state.json", new_state)
    save("feed.json", feed)

    if audio_on and not first_run:
        for kind, text in spoken:
            play(kind)
            speak(text)


def speak_test() -> None:
    play("goal")
    speak("Tooor! Das ist ein Test des Live Kommentators. Die Audio Ausgabe funktioniert.")


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--speak-test":
            speak_test()
        else:
            run_engine()
    except Exception as exc:
        sys.stderr.write(str(exc))
