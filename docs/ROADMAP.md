# Development roadmap

The primary task plan and acceptance checklist is
[FFMPEG_CODEX_ROADMAP.md](../FFMPEG_CODEX_ROADMAP.md).
Follow its task order and completion criteria. The summary below describes the
prototype's existing scope; it does not mark the detailed milestones complete.

Baseline evidence and open issues: [M0 audit](BASELINE_AUDIT.md).
M0.3 is complete: [errors, diagnostics and paths](M0_3_DIAGNOSTICS.md).
M0.4 implementation is committed; hosted Linux/Windows CI verification is pending.
Next: M1 application shell tasks (authorized while the CI check is pending).

1. Bootstrap: PySide6 app, external/bundled binary resolver, FFprobe Inspect [initial scaffold implemented].
2. Domain models for operation/profile/streams, validation, typed command builder; first remux task [initial Matroska/MP4 slice implemented; Windows verification pending].
3. Task runner via QProcess, progress events, cancellation, output safety, queue [basic asynchronous execution and overwrite refusal implemented; progress/cancellation/queue pending].
4. Transcode and compression presets; advanced quality/bitrate options.
5. CPU/GPU capability discovery and runtime validation (NVENC, QSV, VAAPI, etc. as available).
6. Profiles, diagnostics, tests, Windows/Linux packaging and licensing checks.

Before completing a milestone, verify tests and manually exercise on both platforms where possible.
