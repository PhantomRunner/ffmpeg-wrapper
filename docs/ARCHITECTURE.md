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

## Not implemented yet
Transcode/Compress, queue, progress reporting, cancellation, GPU detection, persistent settings, packaging and CI. Codec compatibility beyond the initial conservative remux allowlist remains unsupported. Windows runtime verification is still required.
