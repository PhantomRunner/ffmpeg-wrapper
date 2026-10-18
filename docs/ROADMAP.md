# Development roadmap

## Active UI migration

The functional implementation is the baseline for the new UI-only R1–R6 plan.
Follow [UI overhaul](UI_OVERHAUL_CODEX.md) and [UI/UX specification](UI_UX_SPEC.md).
R1 is complete: [UI migration map](UI_MIGRATION_MAP.md). R2 is complete: [theme and controls](R2_THEME.md).
R3 implementation is verified locally: [workspace evidence](R3_WORKSPACE.md); native Windows acceptance remains pending.
R4 is complete: [Inspector and Library evidence](R4_INSPECTOR.md).
R5 is complete: [dual timeline evidence](R5_TIMELINES.md).
Next phase: R6 polish, regression and rollout.
The notes below retain historical functional/release evidence; they do not extend
the scope of this UI redesign.

## Functional roadmap archive

The primary task plan and acceptance checklist is
[FFMPEG_CODEX_ROADMAP.md](../FFMPEG_CODEX_ROADMAP.md).
Follow its task order and completion criteria. The summary below describes the
prototype's existing scope; it does not mark the detailed milestones complete.

Baseline evidence and open issues: [M0 audit](BASELINE_AUDIT.md).
M0.3 is complete: [errors, diagnostics and paths](M0_3_DIAGNOSTICS.md).
M0.4 implementation is committed; hosted Linux/Windows CI verification is pending.
M1.1–M1.5 are complete: [shell verification](M1_SHELL.md).
M2.1–M2.4 are complete on Linux: [inspection verification](M2_INSPECTION.md).
M3.1–M3.5 are complete on Linux: [command verification](M3_COMMANDS.md).
M4.1–M4.5 and M5.1–M5.5 are complete on Linux: [execution verification](M4_M5_EXECUTION.md).
M5.6 remains deferred until GPU contention tests are possible after M7.
M6.1–M6.5 complete on Linux: [encoding verification](M6_ENCODING.md).
M7.1–M7.6 complete with recorded local coverage: [capability verification](M7_CAPABILITIES.md).
M8.1–M8.6 complete with recorded local coverage: [advanced workflow verification](M8_WORKFLOWS.md).
M9 implementation and local Linux verification recorded in [distribution evidence](M9_DISTRIBUTION.md).
M9.1/M9.4 are complete; native Windows/hosted results, licensing and release gates remain open.
Next: native M9.2/M9.3/M9.5 verification and M9.6 release approval. M10 is not defined. Successful physical GPU encoding
and contention tests remain pending; M5.6 stays open. M0.4 hosted CI remains pending.

1. Bootstrap: PySide6 app, external/bundled binary resolver, FFprobe Inspect [initial scaffold implemented].
2. Domain models for operation/profile/streams, validation, typed command builder; first remux task [initial Matroska/MP4 slice implemented; Windows verification pending].
3. Task runner via QProcess, progress events, cancellation, output safety, queue [asynchronous execution, verified staged Remux, progress/cancellation and sequential session queue implemented].
4. Transcode and compression presets; advanced quality/bitrate options.
5. CPU/GPU capability discovery and runtime validation (NVENC, QSV, VAAPI, etc. as available).
6. Profiles, diagnostics, tests, Windows/Linux packaging and licensing checks.

Before completing a milestone, verify tests and manually exercise on both platforms where possible.
