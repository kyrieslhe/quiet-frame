# Quiet Frame · 留影

A private photographic archive for your own computer. Organize shoots into collections, keep original files, and view or edit locations and EXIF metadata.

English · [中文](README.md)

![Quiet Frame](docs/preview.png)

## Start

Requires **Python 3.9+**. The first launch downloads Python dependencies. Subsequent launches work offline; Node.js and online accounts are unnecessary.

- **macOS:** double-click `启动留影.command`. If macOS blocks it, run `bash 启动留影.command` from the project folder.
- **Windows:** install Python with Python Launcher, then double-click `start.bat`.
- **Linux:** run `sh start.sh`.

The browser opens at <http://127.0.0.1:47321>. Press `Ctrl+C` in the launch terminal to stop the server. Windows and Linux launch scripts have not been tested on their respective operating systems.

## Features

- Collections with editable titles, dates, locations and notes.
- Batch import or drag and drop JPEG, PNG, WebP and TIFF (up to 512 MB per request). Export HEIC / RAW as JPEG first.
- Automatic EXIF parsing: camera, lens, focal length, aperture, shutter, ISO, date and GPS.
- Editable metadata stored separately; original files remain unchanged.
- Gallery and index layouts, grid and sequence browsing, full-size viewer with arrow-key navigation.
- Complete Chinese / English interface. Your own titles and notes retain their original language.
- Light and dark themes. Initially follows the operating system; a manual choice is remembered. Photographs are never recolored.
- Download originals, choose collection covers and export a ZIP backup.

No tracking, remote scripts, external fonts or geocoding. GPS is displayed as editable coordinates rather than automatically looked-up place names. Missing EXIF is left blank. Camera timestamps are shown as recorded, without inferred time zones.

The first-run photograph is explicitly labeled as an Unsplash sample. Your own collections replace it. It is not imported into the archive or assigned fictional metadata. See [third-party notices](THIRD_PARTY_NOTICES.md).

## Storage and backup

`data/archive.sqlite3` stores collection records and metadata; `data/originals/` holds imported copies; `data/previews/` holds generated JPEG previews. The entire `data/` directory is ignored by Git.

The simplest complete backup is to stop the server and copy `data/`. To restore, stop the server and put the saved directory back. ZIP export includes `archive.sql`, originals and previews. Export after imports or deletions finish. For very large archives, copy the data directory rather than creating an in-memory ZIP.

To restore a ZIP, extract it to a new `restored/` folder and run:

```sh
python3 -c "import sqlite3,pathlib; p=pathlib.Path('restored'); c=sqlite3.connect(p/'archive.sqlite3'); c.executescript((p/'archive.sql').read_text(encoding='utf-8')); c.close()"
```

Keep a copy of your current `data/` folder before replacing it with `restored/`. Only restore trusted backups.

## Development

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
python -m unittest discover -s tests -v
```

`PORT` changes the port; `QUIET_FRAME_DATA` sets an alternate data directory; `--no-browser` skips opening the browser. Python, Flask, SQLite, Pillow and buildless HTML/CSS/JavaScript. The server only listens on loopback and validates Host and write tokens. Intended for local, single-user use.

## License

Code: MIT. The bundled sample photograph and screenshots containing it are subject to the Unsplash License. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
