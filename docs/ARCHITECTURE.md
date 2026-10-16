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
- Qt-independent task states and application sequential queue with cancellation,
  fresh-attempt retry and per-task logs/results. Queue state is session-only.
- Desktop navigation with independent Files/Inspect, Remux and Settings pages;
  Queue page; placeholder Convert/Compress pages.
- DesktopState and DesktopViewModel own selection, validation and asynchronous
  lifecycle state. Widgets bind state and actions; workers invoke services.
- Local multi-file selection/drop, current-file inspection, safe output forms and
  asynchronous generated-command preview. Execution always validates again.
- Versioned preferences: domain schema, application preservation policy and an
  infrastructure repository that writes atomically in the native config folder.

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
Transcode/Compress UI, parallel queue execution, GPU detection and packaging. CI workflow is configured; hosted execution is pending. Codec compatibility beyond the initial conservative remux allowlist remains unsupported. Windows runtime verification is still required.
