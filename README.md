# FFmpeg UI Wrapper

Cross-platform desktop frontend for FFmpeg with advanced media workflows. **Early MVP:** detects FFmpeg/FFprobe, inspects media metadata, and remuxes supported streams into Matroska or MP4. Transcoding and compression are not implemented yet.

## Requirements
- Python 3.11 or later
- Linux or Windows
- FFmpeg and FFprobe installed and on PATH, or available in one directory selected within the application

## Run (PyCharm terminal or OS terminal)

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

## Using in PyCharm and Codex
1. Open this project root in PyCharm.
2. Configure the project interpreter as `.venv` (create one if needed).
3. Run module `media_wrapper.main`.
4. Codex should follow the repository `AGENTS.md` file. Architectural decisions are recorded under `docs/`.

## Current user flow
Select external mode (PATH or choose bin folder) or bundled (choose folder), click Detect FFmpeg, then Open media file and inspect. Select Matroska or MP4 and click **Remux inspected file…** to choose a new destination.

Remux copies all streams without re-encoding. This initial slice uses a conservative codec/container allowlist; unsupported streams are reported rather than dropped. Both the application and FFmpeg refuse existing destinations. If an operation fails, a partial output may remain; inspect or remove it yourself, or choose a new filename to retry. Wait for the current operation to finish before closing. Cancellation and progress reporting are planned.

Tests include offscreen Qt lifecycle checks and tiny real-media integration checks. FFmpeg integration tests skip when the binaries are unavailable.

## Diagnostics and application directories

Startup shows the diagnostic log location in the status bar. Failures include a
recovery suggestion; technical details and tracebacks are written to a UTF-8 log.
Logs rotate at 1 MiB with three backups and are written on a background thread.
They can contain local media paths and FFmpeg diagnostics; review them before sharing.
If the log directory cannot be opened, the status bar reports the problem and
diagnostics go to stderr. Run from a terminal to read that fallback output.

Locations come from Qt's native per-user directory APIs with application name
`MediaWrapper`:

- Linux: config normally `$XDG_CONFIG_HOME/MediaWrapper` (default
  `~/.config/MediaWrapper`); logs normally under
  `$XDG_DATA_HOME/MediaWrapper/logs` (default `~/.local/share/MediaWrapper/logs`).
- Windows: config uses Qt `AppConfigLocation` and logs use
  `AppLocalDataLocation/logs`, normally under `%LOCALAPPDATA%/MediaWrapper`.
- The log filename is `media-wrapper.log`. `settings.json` is reserved under the
  config directory; settings persistence is not implemented and no settings file
  is created by this change.

The displayed location is authoritative if the OS redirects these directories.
Windows runtime verification remains pending.

## Important
Bundled mode is prepared but no FFmpeg binaries are shipped in this repository. Distribution must account for FFmpeg licensing and build configuration.
