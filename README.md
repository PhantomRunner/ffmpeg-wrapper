# FFmpeg UI Wrapper

MVP early access Cross-platform UI for FFmpeg in development process.

Deployed features:
- media metadata inspection
- remux into Matroska, MP4, MOV, WebM, WAV or FLAC containers
- Converting and Compress, 
- Quality/bitrate controls.
- Source preview

## Requirements
- Python 3.11 or later
- Docker
- FFmpeg and FFprobe installed and on PATH, or available in one directory selected within the application

## Use (PyCharm terminal or OS terminal)

Windows compatibility not verified, still in development
```bash
python -m venv .venv
```

Activate environment on Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install and launch:

```bash
python -m pip install -e ".[dev]"
python -m media_wrapper.main
```

Run tests:

```bash
python -m pytest -q
```
