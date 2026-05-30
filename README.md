# WM 2026 Widget — Windows / Lively Wallpaper

Windows-Port des macOS-`Übersicht`-Widgets, angepasst für `Lively Wallpaper`.

## Enthalten

- gleiche Sidebar-Optik wie das macOS-Widget
- Live-Scores, kompletter Spielplan, Countdown
- Live-Audio mit `mpv`
- deutsche Tor-/Anpfiff-/Abpfiff-Kommentare per Windows-TTS
- ESPN-Kommentarfeed + kicker-Kommentare
- einklappbares Widget, Side-Panel und optionaler Desktop-Icon-Shift
- Hintergrund übernimmt automatisch das aktuelle Windows-Wallpaper, damit das Widget wie ein Overlay wirkt

## Voraussetzungen

- Windows 10 oder 11
- [Lively Wallpaper](https://livelywallpaper.app/)
- Python 3.10+
- `mpv` im `PATH` oder in einem Standardpfad

## Installation

```powershell
cd "WM2026 widget WINDOWS"
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Danach:

1. `Lively Wallpaper` öffnen.
2. Den Ordner [`widget`](/Volumes/NAS/Mac-Auslagerung/Desktop/Claude/Github%20Projekt/WM2026%20widget%20WINDOWS/widget) per Drag & Drop in Lively importieren.
3. [`start_server.bat`](/Volumes/NAS/Mac-Auslagerung/Desktop/Claude/Github%20Projekt/WM2026%20widget%20WINDOWS/start_server.bat) oder [`start_server_hidden.vbs`](/Volumes/NAS/Mac-Auslagerung/Desktop/Claude/Github%20Projekt/WM2026%20widget%20WINDOWS/start_server_hidden.vbs) starten.
4. Das Wallpaper in Lively aktivieren.

## Desktop-Shift konfigurieren

Wenn sich beim Oeffnen des Ticker-Panels Desktop-Icons verschieben sollen:

```powershell
copy "$env:APPDATA\wm2026\shift_config.example.json" "$env:APPDATA\wm2026\shift_config.json"
```

Dann in `shift_config.json` die exakten Icon-Namen und Zielpositionen anpassen.

Wichtig:

- `Automatisch anordnen` und `Am Raster ausrichten` auf dem Windows-Desktop sollten deaktiviert sein, sonst setzt Windows die Positionen eventuell wieder zurueck.
- Die Funktion nutzt die offizielle Windows-Shell-Ordneransicht und benoetigt `pywin32`.

## Datenordner

Alle Laufzeitdaten landen in:

```text
%APPDATA%\wm2026
```
