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
- FFprobe inspection (JSON parser, background Qt worker).
- Background binary detection through an application use case.
- Typed remux request, streams and container enum; pure argument-array command builder.
- Conservative Matroska/MP4 compatibility validation, all-stream copy, explicit stream mapping.
- Asynchronous QProcess remux execution, bounded diagnostics, and overwrite refusal. Failed partial files are retained and reported.
- Minimal Qt desktop main window.

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
- Settings persistence is deferred; only the settings path is defined. No config
  directory or settings file is created merely by resolving the location.
- Source functions and UI/task callbacks have explicit parameter/return annotations;
  dynamic FFprobe payloads remain typed as raw dictionaries until M2.

## Not implemented yet
Transcode/Compress, queue, progress reporting, cancellation, GPU detection, persistent settings, packaging. CI workflow is configured; hosted execution is pending. Codec compatibility beyond the initial conservative remux allowlist remains unsupported. Windows runtime verification is still required.
