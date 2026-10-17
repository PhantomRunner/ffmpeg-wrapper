# Architecture

## Goal
A desktop frontend for FFmpeg operations (Inspect, Remux, Transcode, Compress, batch processing) on Linux and Windows. Audience: advanced users; CPU and GPU encoders; bundled and external FFmpeg.

## Layers
- `domain`: media, streams, profiles, task states; no Qt imports.
- `application`: inspection orchestration, binary detection, remux validation, and a Qt task adapter.
- `infrastructure/ffmpeg`: binary resolution, FFprobe JSON parsing, command builder, process runner, capability detector.
- `ui`: PySide6 Qt Widgets, models, dialogs; signals and slots, no blocking subprocesses on UI thread.

## Rules
- FFmpeg commands are arrays of arguments, not shell strings.
- Remux: stream copy only where destination container accepts streams.
- GPU discovery checks listed encoders and optionally confirms with runtime tests.
- Progress: `-progress pipe:1`, parse `key=value` lines.
- In/out paths validated, avoid accidental overwrite, sanitize temp outputs.
- Integration tests use tiny media fixtures; CI runs on Linux and Windows.

## Implemented in scaffold
- Binary resolution (external PATH or custom folder, bundled explicit folder).
- Version diagnostics.
- Typed immutable MediaFile/MediaStream entities; infrastructure parses FFprobe JSON
  and rational frame rates, preserving missing metadata explicitly.
- Sequential multi-file inspection on a Qt worker with per-file outcomes, cached
  results/stream selections and cancellable subprocess cleanup.
- Background binary detection through an application use case.
- Typed immutable operation plans, per-stream encoding profiles, output targets and
  validation errors in domain; pure policy validation independent of filesystem/Qt.
- Application validates filesystem safety and prepares optional staged output paths.
  Pure CommandBuilder generates deterministic maps and copy/encoding arguments.
  Remux executes typed plans through a shared asynchronous process runner.
- Conservative Matroska/MP4 compatibility validation, user-selected stream copy and explicit mapping.
- Asynchronous QProcess execution, separate stdout/stderr, incremental progress,
  terminate/kill cancellation and bounded diagnostics. Workers prepare and verify
  output before no-overwrite hard-link publication; partial files are retained.
- Per-build capability inventory is cached by executable identity/version. Settings
  runs optional cancellable synthetic GPU tests; reports distinguish listing from
  runtime success. CPU/GPU/Auto planning uses tested evidence; execution rechecks
  GPU initialization. Failed GPU attempts require explicit user CPU retry.
- CPU encoding supports H.264/H.265, AAC, PCM and FFV1 with selected-track mapping,
  scaling/FPS, CRF/bitrate controls and editable presets. Target-size mode estimates
  bitrate for two-pass H.264. Both passes share cancellation and output safety.
- Qt-independent task states and application sequential queue with cancellation,
  fresh-attempt retry and per-task logs/results. Task history is session-only; explicit versioned queue definitions recreate validated pending attempts.
- Desktop navigation with independent Files/Inspect, Remux and Settings pages;
  Queue, Convert and Compress pages.
- DesktopState and DesktopViewModel own selection, validation and asynchronous
  lifecycle state. Widgets bind state and actions; workers invoke services.
- Local multi-file selection/drop, current-file inspection, safe output forms and
  asynchronous generated-command preview. Execution always validates again.
- Versioned preferences: domain schema, application preservation policy and an
  infrastructure repository that writes atomically in the native config folder.

## Advanced workflows (M8)

- Domain owns versioned profile/queue schemas, preservation policies and a strict
  two-option custom-argument grammar. No Qt or filesystem calls enter domain.
- Application services validate profiles against the selected build, plan entire
  batches, snapshot allowlisted diagnostics, and revalidate imported queue files.
  Definitions contain intent and source size/mtime, never executables or process
  state. Queue import preserves explicit hardware choices; execution repeats GPU
  runtime checks. Imported jobs do not auto-start.
- Infrastructure reads bounded strict JSON and creates exports exclusively,
  preserving existing files. UI invokes document/batch services on Qt workers.
- FFprobe parses global tags, chapters and stream codec tags. CommandBuilder
  emits explicit metadata/chapter maps and validated custom options. Publication
  verifies chapter count/removal and media streams; MP4's specific generated
  QuickTime chapter track is recognized without ignoring other extra streams.
- Settings stores a log level; diagnostics exports omit paths, raw logs/errors,
  arguments and metadata unless the user explicitly enables private details.

## Error and diagnostic policy (M0.3)

- Application services translate implementation exceptions into `ApplicationError`,
  retaining the original cause. User guidance and technical details are separate.
- Worker and task boundaries log each failure once and send the normalized message
  to the UI. Unexpected exceptions are logged with tracebacks; process failures
  retain the available FFmpeg diagnostics and exit code.
- `main.py` sets the Qt application identity and composes infrastructure path/log
  setup. `AppPaths` uses `pathlib.Path` and Qt `AppConfigLocation` /
  `AppLocalDataLocation`; resolving a path has no filesystem side effects.
- A QueueHandler/QueueListener writes rotating UTF-8 logs outside the UI thread.
  Shutdown drains the listener. A startup file-open failure falls back explicitly
  to stderr and is shown in the status bar. Rotation limits each file to about
  1 MiB plus three backups (an individual oversized record can exceed the limit).
- M1.5 adds version-1 preferences in `settings.json`. Paths are still resolved
  without side effects; the config directory is created only when saving.
  Malformed/unsupported settings disable saving and remain untouched. A pre-save
  read detects external edits; atomic replacement protects against incomplete writes.
  Concurrent writers are not locked across the read-and-replace interval.
- Source functions and UI/task callbacks have explicit parameter/return annotations;
  dynamic FFprobe payloads are parsed into Qt-independent typed entities.

## Not implemented yet
Parallel queue execution and release-approved distribution. Native PyInstaller portable build recipes and installation verification are implemented; hosted and Windows execution are pending. Codec compatibility beyond the initial conservative remux allowlist remains unsupported. Windows runtime verification is still required.

## Distribution (M9 candidate)

- Native one-folder PyInstaller builds retain the Qt Widgets architecture and
  include resources/docs, dependency metadata, license inventory and file hashes.
  FFmpeg remains external or explicitly selected from a user-supplied sidecar.
- Infrastructure restores external subprocess library-search environments in
  frozen builds; Windows DLL-search initialization occurs after Qt loads.
- The explicit installation-verification entry point is UI automation composed
  over the existing asynchronous model/services, with isolated preferences and
  generated fixtures; production workflows are not replaced.
- CI has separate source-test and native distribution jobs. Public distribution
  stays gated on native results, application license choice and dependency review.
