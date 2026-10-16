# M0 baseline audit — 2026-10-16

Scope: M0.1 and M0.2 only. No runtime features were added or changed.
The primary plan is [FFMPEG_CODEX_ROADMAP.md](../FFMPEG_CODEX_ROADMAP.md).
The repository initially had no commits; this audit establishes an initial
versioned baseline containing the existing application, tests and project docs.
`.gitignore` excludes environments, bytecode, test caches and local IDE/agent state.

## Actual implementation and boundaries (M0.1)

- `main.py` creates a PySide6 QApplication and MainWindow; the installed
  `media-wrapper` console command calls the same entry point.
- `domain/` contains Qt-independent media metadata, stream, container and remux
  request dataclasses. MediaInfo still stores raw stream dictionaries.
- `application/` exposes binary detection and inspection/remux preparation.
  Its RemuxTask is an explicitly Qt-aware adapter around infrastructure.
- `infrastructure/ffmpeg/` resolves external PATH/custom-folder or explicit
  bundled-folder binaries, checks both versions, invokes FFprobe and parses JSON,
  builds argument arrays, and runs remux asynchronously through QProcess.
- `ui/` uses services and background QThread workers for detection, inspection
  and remux preparation. Widgets do not build FFmpeg commands or invoke subprocesses.
- The UI supports one inspected file and Matroska/MP4 all-stream copy through a
  conservative codec allowlist. It rejects unsupported streams and existing output
  names. Commands use explicit maps, `-c copy`, `-n`, and no command shell.
- Failed partial output is retained with an explanatory message. Closing is
  prevented while an operation is active. There is no cancellation.

README largely describes the current behavior accurately. The older short roadmap
and detailed roadmap were disconnected; docs/ROADMAP.md now links to the detailed
checklist. The architecture describes intended CI, but no CI configuration exists.
The initial Remux prototype does not satisfy all detailed M3/M4/M5 acceptance criteria.

## Verification (M0.2)

Development machine: Linux x86_64, Python 3.14.8, PySide6 6.12.0, pytest 9.1.1,
Ruff 0.17.1, FFmpeg/FFprobe n9.0.2. A new venv was created without system packages;
project dependencies were installed via the declared build backend and dev extra.
No changes were made to the existing development environment.

Commands run from the repository root (temporary directory retained for evidence):

```bash
python -m venv /tmp/ffmpeg-m0-audit-XMLHiB/venv
/tmp/ffmpeg-m0-audit-XMLHiB/venv/bin/python -m pip install -e '.[dev]'
PYTHONDONTWRITEBYTECODE=1 /tmp/ffmpeg-m0-audit-XMLHiB/venv/bin/python -m pytest -q -p no:cacheprovider
/tmp/ffmpeg-m0-audit-XMLHiB/venv/bin/python -m pip check
/tmp/ffmpeg-m0-audit-XMLHiB/venv/bin/python -m ruff check . --no-cache
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 timeout 3s /tmp/ffmpeg-m0-audit-XMLHiB/venv/bin/python -m media_wrapper.main
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 timeout 3s /tmp/ffmpeg-m0-audit-XMLHiB/venv/bin/media-wrapper
```

Results: editable install succeeded; **24 tests passed, no skips**; dependency check
reported no broken requirements; lint passed. Both entry points ran until timeout
(exit 124, expected for these bounded startup checks), with only offscreen plugin
size-hint warnings. These timeout checks prove startup, not graceful shutdown.
The existing Qt integration test separately verifies worker completion, UI state
restoration and normal window close after Inspect and Remux. It uses generated PCM
WAV media, creates Matroska output with a Unicode/space path, and verifies overwrite
refusal. The service integration test probes the remuxed PCM codec and confirms an
existing destination remains byte-for-byte unchanged.

### Clean staged snapshot

Before the first commit, exported only staged files into an empty directory and
created a second independent venv. This verifies the intended checkout contents,
without the working tree's `.venv`, caches or IDE state:

```bash
git checkout-index --all --prefix=/tmp/ffmpeg-m0-audit-XMLHiB/checkout/
python -m venv /tmp/ffmpeg-m0-audit-XMLHiB/clean-venv
cd /tmp/ffmpeg-m0-audit-XMLHiB/checkout
../clean-venv/bin/python -m pip install -e '.[dev]'
PYTHONDONTWRITEBYTECODE=1 ../clean-venv/bin/python -m pytest -q -p no:cacheprovider
../clean-venv/bin/python -m ruff check . --no-cache
../clean-venv/bin/python -m pip check
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 timeout 3s ../clean-venv/bin/python -m media_wrapper.main
```

Results: install succeeded; **24 passed, no skips**; lint and dependency checks
passed; module startup stayed alive until the expected timeout (124).
Python emitted prefix-normalization warnings for the relative `../clean-venv`
interpreter path. An absolute-path check with warnings treated as errors passed:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/ffmpeg-m0-audit-XMLHiB/clean-venv/bin/python -W error -c "import sys, media_wrapper, PySide6; print('Clean environment:', sys.prefix); print('Installed source:', media_wrapper.__file__)"
```

It confirmed that imports came from the clean exported source tree. Use an absolute
interpreter path to avoid this development-Python warning. Final changes after
snapshot verification were limited to this evidence and roadmap status.

## Findings and follow-up

| Finding | Evidence / impact | Follow-up |
| --- | --- | --- |
| No normalized errors, logging or config path; incomplete annotations | Exceptions become UI strings; diagnostics are not persisted, configuration is not saved | M0.3 |
| Non-finite durations accepted | MediaInfo.from_probe with duration `NaN` or `Infinity` returns nan/inf; malformed nested shapes are not validated | M0.4 baseline tests, M2 typed parsing |
| Stream labels use enumeration | InspectionWorker displays the tuple position rather than FFprobe's actual `index` | M2.2 |
| Probe paths are not normalized | A relative source beginning with `-` can be interpreted as an FFprobe option; desktop file dialogs normally return absolute paths | M0.4 path tests and targeted fix |
| Partial command validation | A directly constructed Stream(True, ...) produces `-map 0:True`; parser validation does not protect every builder caller | M3.2/M3.5 |
| Builder is not fully pure | It calls Path.resolve() against the filesystem; validation and serialization overlap | M3.2/M3.3 |
| Process runner is effectively single-use | `_done` and diagnostic tail are not reset on start; current UI creates a new task per operation | M5.1 |
| Completion relies on exit status and diagnostic substrings | No final media validation; matching text in filenames can affect classification; no structured result with exit code | M4.4/M5.1 |
| Outputs are written directly to final names | `-n` and application checks refuse existing destinations, but failed partial files remain; no atomic finalization or cancellation | M3.4/M4.3/M5 |
| Codec policy is static | Conservative allowlist is not a per-build muxer/codec capability check | M3.2/M7 |
| Baseline negative tests are sparse | Resolver tests cover only invalid mode and missing bundled directory; missing executables, failed versions, malformed probe JSON and failed probes need coverage | M0.4 |
| Broader features absent | No selected-track UI, command preview, progress, queue, transcode, compression, capabilities, persistence or packaging | Follow detailed roadmap |

Confirmed by read-only reproductions: non-finite durations and boolean stream index
acceptance. Other findings are identified from source review; they are not claims
that a platform failure was reproduced. This audit deliberately records issues
without implementing subsequent milestone features.

## Platform and acceptance limits

M0.1 and M0.2 are complete for the development machine. Linux clean install,
automated tests and offscreen Qt behavior are verified.
Interactive native dialogs, display rendering and manual desktop use were not
verified. Windows runtime/install behavior and Python 3.11 were not available to
test; no cross-platform success is claimed. No GPU or bundled distribution was
tested. Explicit folder resolution exists but has not yet received comprehensive
baseline coverage. M0 remains incomplete until M0.3 and M0.4 are satisfied.

Next task: **M0.3**, starting with a small slice that defines shared application
errors and routes worker failures through consistent UI messages and diagnostic
logging, with negative-path tests. Then establish portable config-path handling
and annotations. M0.4 follows with resolver/probe/path tests and Linux/Windows CI.
