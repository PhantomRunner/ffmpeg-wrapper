# FFmpeg UI Wrapper

Cross-platform desktop frontend for FFmpeg with advanced media workflows. Detects FFmpeg/FFprobe, inspects media metadata, and remuxes compatible selected streams into Matroska, MP4, MOV, WebM, WAV or FLAC. Convert and Compress support CPU encoding, quality/bitrate controls and H.264 two-pass size estimates.

The default interface is a dark, resizable media workstation with a persistent
Library, contextual operation Inspector and standalone Queue page.
[Current UX plan and verification evidence](docs/UX_REMEDIATION_PLAN.md).
Source preview supports Play/Pause, position/duration and seeking. Preview uses Qt Multimedia codecs independently of the selected
processing FFmpeg build; unsupported media/backend errors are shown explicitly.

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
1. In **Settings**, select external (PATH or custom folder) or bundled (explicit folder) and detect FFmpeg. Startup also detects the saved installation.
2. In **Inspect / Media Library**, add multiple files or drop local files. Select a current file and click **Inspect current file**, or select several and click **Inspect selected files**. **Cancel inspection** stops the active probe and cancels pending files while retaining completed results. Select a row to review its metadata and stream table. **Clear files** clears the selection and inspected source.
3. In **Remux**, check the video/audio/subtitle tracks to copy, choose a compatible container and a new destination (the filename extension follows container changes). Inline validation explains unsafe or invalid paths. **Advanced details → Validate and preview** shows the generated argument array without creating output.
4. Click **Run remux**, or **Add to queue** and start it on the **Queue** page. Execution probes and validates again. Progress includes estimated speed/ETA; cancellation waits for process cleanup. Successful output is verified before publication.

Convert prioritizes container, per-track copy/omit/encoding, resolution and FPS. Compress prioritizes quality, bitrate or target size, speed presets and output-size estimates; stream choices and detailed controls are expandable. Presets remain editable. Preview validates the selected build; Run executes through Queue with cancellation and verified output. Quality modes trade size against quality; target-size mode estimates a size and never guarantees it. Inspection supports sequential batches with per-file results. Stream checkbox selections are used by Remux. Convert/Compress can plan batches from the selected Files rows.

Remux copies the selected streams without re-encoding. The container registry uses conservative codec/count/chapter rules; unsupported streams are reported rather than dropped. Both the application and FFmpeg refuse existing destinations. Output is written to an adjacent hidden temporary file, verified, then published without replacing an existing destination. Publication requires hard-link support on that filesystem; failure retains the temporary file. Failed or cancelled partial files are retained and reported; inspect or remove them yourself. Cancel or wait for active work to finish before closing.

The sequential Queue shows status, output paths, progress, arguments, verified results and diagnostic tails. Failed/cancelled jobs do not stop later jobs. Retry creates a fresh attempt and temporary path, preserving history; resolve destination collisions before retrying. Queue history lasts for the current session; unfinished definitions can be saved and reloaded explicitly. After an application/OS crash, partial files may remain beside the destination. Parallel execution awaits GPU contention testing.

Tests include offscreen Qt lifecycle checks and tiny real-media integration checks. FFmpeg integration tests skip locally when the binaries are unavailable. The CI workflow requires FFmpeg before running the Linux/Windows test matrix. A Git remote is configured; hosted execution of the current workflows remains pending.

## Advanced workflows

- **Profiles:** Save/export editable Convert/Compress choices as versioned JSON.
  Import checks track indices and the selected build, then opens the matching
  form for review. Profiles exclude source/destination paths. Numeric values must
  fit the form's supported ranges and units; GPU preferences require a current
  successful runtime scan. Unsupported versions/settings are rejected.
- **Batch:** Select Files rows, inspect a representative source and configure
  Convert/Compress. Set an existing output folder and a filename template using
  `{stem}`, `{index}` and `{ext}`. Add the batch, review Queue, then start it.
  Every source is probed; incompatible tracks or colliding outputs reject the
  entire batch. Track indices must have the intended meaning in every source.
- **Streams:** Enter all selected real indices to control output order. Text
  subtitles can be copied or converted to supported container formats. Bitmap
  subtitles require compatible copying or explicit omission. Preserve/strip
  controls apply to global/track metadata and chapters; metadata support depends
  on the container, and muxers may generate their own tags. MP4 chapter output
  may contain a generated data track; omit that data track when processing the
  output again, while preserving chapters through the chapter control.
- **Custom options:** Only `-threads 1–64` and
  `-max_muxing_queue_size 1–65536` are accepted, once each. Preview validates and
  displays them. Input/output/mapping/filter/overwrite options are rejected.
- **Queue definitions:** Save unfinished jobs to a new JSON file before closing.
  This file contains local paths. Load re-probes unchanged sources, validates
  against the current binaries and rejects existing/conflicting outputs. It
  creates fresh pending attempts; press Start explicitly. Changed sources need
  fresh inspection/planning. There are no mid-encode checkpoints or automatic
  queue backups, and absolute paths must be valid on the current OS.
- **Diagnostics:** Settings controls the local logging level and exports a
  privacy-safe task summary. Private paths, arguments and raw logs are included
  only when the labeled checkbox is enabled. All exports refuse existing files.

## CPU and GPU selection
In Settings, **Scan build / refresh capabilities** reads the selected FFmpeg build.
Enable the optional runtime test checkbox to try short synthetic GPU encodes.
VAAPI needs an explicit render device. Listing an encoder or hardware API does
not mean it works: the report distinguishes untested, working and unavailable.

Convert/Compress offers **CPU**, **GPU**, and **Auto**. GPU uses a matching tested
H.264/HEVC encoder; Auto chooses a tested match or records its CPU choice. GPU
supports default/bitrate modes here; CRF and target-size/two-pass use CPU. Preview
and Queue show the actual arguments. Execution rechecks GPU initialization. If a
GPU job fails, **Retry on CPU** explicitly creates a fresh attempt and preserves
old diagnostics/partial output. There is no silent runtime fallback.

This environment verified GPU failure detection but had no usable GPU. Successful
physical GPU encoding and Windows runtime coverage remain pending. See
[capability verification](docs/M7_CAPABILITIES.md) for the exact coverage.

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
- The log filename is `media-wrapper.log`. `settings.json` under the config
  directory stores version-1 preferences on normal close: binary mode/folder,
  recent destination, container, advanced details, current page, window size and log level.
  Selected media files and running operations are not persisted.

Preferences are saved atomically. Invalid, unknown-version, or externally changed
settings are preserved; the UI reports load/save failures. Repair or remove an
incompatible settings file yourself before restarting to save new preferences.

The displayed location is authoritative if the OS redirects these directories.
Windows runtime verification remains pending.

## Important
Bundled mode is prepared but no FFmpeg binaries are shipped in this repository. Distribution must account for FFmpeg licensing and build configuration.

## Distribution candidates

Native portable build and verification instructions are in
[docs/DISTRIBUTION.md](docs/DISTRIBUTION.md). The Linux candidate passed local
installation/removal and packaged Inspect/Remux/Convert/Compress checks. Windows
verification and public release approval remain pending. No FFmpeg binaries are
bundled. See [release gates](docs/RELEASE_CHECKLIST.md),
[third-party notices](THIRD_PARTY_NOTICES.md), and [candidate notes](CHANGELOG.md).

## Workstation shortcuts and layout

- Ctrl+O: import local media and inspect it in the background.
- Alt+1…6: Inspect, Remux, Convert, Compress, Queue, Settings.
- Ctrl+Enter: start pending queue jobs.
- Ctrl+Shift+L: reset the current splitter layout; per-operation layouts persist on close.

Operation actions stay visible while the Inspector scrolls. Expand **Advanced
settings and batch** for detailed encoding controls and batch options.
Processing jobs are available on the standalone **Queue** page. There are no
timeline panels in any workspace layout.

## Workspace and preview

Each operation has its own resizable workspace layout, remembered separately. Queue
uses the main processing area and Settings uses the configuration area. Reset layout
resets the current mode. Remux/Convert/Compress retain edits while switching modes.
Changing the container proposes a matching extension; manual incompatible extensions,
existing outputs and source replacement still fail validation. Long dropdown items
use screen-bounded popups, scrolling and full-text tooltips.

Preview transport supports keyboard and mouse slider seeking. Export ranges are not edited. Qt Multimedia may use its own FFmpeg shared libraries;
processing always uses the explicitly selected external/sidecar executables. Native
Windows, physical audio/display/GPU and public release approval remain pending.

Output size is shown next to Ready in the status bar for Remux, Convert, Compress
and the selected Queue job. Bitrate/target estimates include a 2% muxing allowance;
full stream-copy may use source size when stream rates are unknown. Quality-based
encoding and unknown partial-track rates show a variable size instead of a false
number. Resizable panes have rounded outlines and visible drag handles.

Docker build and container verification: [Docker workflow](docs/DOCKER.md).
