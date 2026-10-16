# FFmpeg UI Wrapper — Codex Implementation Roadmap

Status: **M0.1–M0.3 verified on Linux; M0.4 implemented, hosted CI verification pending; M1.1–M1.5 and M2.1–M2.4 complete on Linux**. Target: **Python 3.11+, PySide6 / Qt Widgets**, Linux and Windows. FFmpeg and FFprobe run as external processes. Audience: advanced users. Support **bundled and external binary modes**, and **CPU/GPU encoding when available**.

> **Instructions for Codex:** First inspect the repository, `AGENTS.md`, and `docs/ARCHITECTURE.md`. Determine actual implemented behavior by reading code/tests; do not assume a checklist item is complete. Work on **one small task or vertical slice at a time**. Keep the app runnable. Mark `[x]` only after acceptance criteria have been met, tests have run, and limitations have been recorded. If a platform/hardware test is unavailable, report it explicitly instead of claiming success. After finishing a task, commit its progress

## Definition of Done (every task)

- [ ] Implementation respects the domain/application/infrastructure/UI boundaries.
- [ ] New logic has appropriate automated tests (including negative/error cases).
- [ ] No long-running work blocks the Qt event loop.
- [ ] FFmpeg/FFprobe invoked with argument arrays, never with `shell=True`.
- [ ] No silent overwrite, source replacement, or deletion of user files.
- [ ] User-facing failures produce actionable errors and log diagnostics.
- [ ] `pytest` passes; run `ruff check .` if configured, or document blockers.
- [ ] Manually verify relevant behavior where possible; record untested platforms/hardware.
- [ ] Update docs and checkboxes in this file.

## Milestone 0 — Baseline audit and cleanup (P0)

Scaffold already contains: `main.py`, a PySide6 window, basic FFmpeg/FFprobe discovery, `ProbeService`, a media model, and initial tests. **Not yet validated as production-ready.**

- [x] **M0.1** Audit the existing source tree against `README.md`, `AGENTS.md`, and architectural boundaries. Write down actual working features and gaps.
- [x] **M0.2** Verify clean install (`python -m pip install -e '.[dev]'`), entry point (`python -m media_wrapper.main`) and `pytest` on the development machine.
- [x] **M0.3** Normalize error reporting, type annotations, logging, and config location; keep filesystem handling portable with `pathlib`.
- [ ] **M0.4** Add baseline automated tests for binary resolution, probe JSON parsing, invalid input, and path handling. Add CI checks for Linux and Windows (tests run on both; GUI smoke test where possible).

**M0.4 implementation:** 75 local tests pass, including resolver/probe/path errors.
`.github/workflows/tests.yml` adds Linux/Windows and Python 3.11/3.14 checks.
No Git remote or Windows runner is available: the checkbox remains open until
CI has actually passed on both platforms. Proceeding to M1 is user-authorized.

**Audit evidence:** see [docs/BASELINE_AUDIT.md](docs/BASELINE_AUDIT.md) for
verified features, commands, gaps, and platform limitations. M0 as a whole remains
open until M0.4 is completed. [M0.3 evidence](docs/M0_3_DIAGNOSTICS.md):
51 tests passed, lint passed; native Windows execution remains unverified. Existing Remux code does not imply that
M3–M5 acceptance criteria are met.

**Acceptance:** a clean checkout starts; the Inspect feature works on a test clip; basic tests pass. Record what could not be verified on Windows/Linux separately.

## Milestone 1 — Application shell and UX foundation (P1)

- [x] **M1.1** Split the main window into navigation and independent views (Files / Inspect, Remux, Convert, Compress, Queue, Settings). Pages can initially be placeholders.
- [x] **M1.2** Introduce UI state / view models; views must call application services, not build FFmpeg commands or invoke processes themselves.
- [x] **M1.3** Add file picker, multi-file selection, drag and drop, recent destination directory, and clear selected-file state.
- [x] **M1.4** Add advanced-friendly input controls: simple/advanced settings groups, form validation, explanatory tooltips, and a read-only command preview (later filled by command builder).
- [x] **M1.5** Persist UI preferences with a versioned settings schema and platform-appropriate config directory.

**M1 evidence:** [shell verification](docs/M1_SHELL.md); 107 local tests pass,
including real Inspect/Remux, asynchronous failure recovery, file/drop/form flows
and preference persistence. Windows execution remains pending.

**Acceptance:** navigation works without breaking Inspect; UI remains responsive; no encoding logic lives in widgets.

## Milestone 2 — Robust media inspection (P1)

- [x] **M2.1** Parse `ffprobe -v error -show_format -show_streams -of json` into Qt-independent typed `MediaFile` / `MediaStream` models.
- [x] **M2.2** Show container, duration, file size, bitrate, frame size, frame rate (rational-safe), codecs, language, audio channels, subtitle types, and stream indices. Treat missing fields as normal.
- [x] **M2.3** Inspect multiple files asynchronously with cancellation, error states, and no GUI freeze.
- [x] **M2.4** Tests for audio-only, video-only, multi-track, missing metadata, malformed JSON, and failed probe invocations.

**M2 evidence:** [inspection verification](docs/M2_INSPECTION.md); 141 local tests
pass, including real audio/video/multi-track fixtures, cancellation and failure
isolation. Offscreen layout reviewed; native Windows execution remains pending.

**Acceptance:** users can inspect multiple sample media files and select individual streams for future operations.

## Milestone 3 — Typed operation model and command builder (P0, required by M4–M7)

- [x] **M3.1** Define `MediaOperation`, `StreamSelection`, `OutputTarget`, `EncodingProfile`, `OperationPlan`, and typed validation errors in `domain/`.
- [x] **M3.2** Implement separate validation for input existence, output naming, in-place/overwrite safety, container–stream compatibility, selected streams, and option availability.
- [x] **M3.3** Implement pure `CommandBuilder`: validated operation plan -> `list[str]` arguments. Never use shell execution; correctly handle spaces/Unicode paths.
- [x] **M3.4** Explicitly map streams (`-map`), support stream-copy plans (`-c copy`), add controlled output overwrite policy (`-n` by default), and isolate temp output from final output.
- [ ] **M3.5** Unit tests for argument generation, conflicting options, missing streams, unsafe destinations, and unsupported container choices.

**Acceptance:** fully deterministic, testable argument arrays for Remux and minimal Convert scenarios, independent of Qt.

## Milestone 4 — Remux vertical slice (P0)

- [ ] **M4.1** Add output container selection and chosen video/audio/subtitle tracks to Remux view.
- [ ] **M4.2** Validate stream compatibility; show clear warnings for unsupported tracks rather than silently dropping them.
- [ ] **M4.3** Execute stream-copy via common process runner (from M5.1); use a temporary output file where appropriate and finalize only on success.
- [ ] **M4.4** Show the exact generated arguments, warnings, result path, and verified output metadata.
- [ ] **M4.5** End-to-end tests using generated small media fixtures; test successful compatible remux and rejected/failed remux.

**Acceptance:** select compatible source -> select MP4/MKV -> remux without re-encoding -> inspect result; unsafe/unsupported cases fail clearly. MVP first complete operation.

## Milestone 5 — Process runner, progress, and task queue (P0; build minimum before M4.3)

- [ ] **M5.1** Build Qt-aware `ProcessRunner` with `QProcess`, stdout/stderr handling, start failure reporting, exit codes, and clean shutdown. Never block the UI.
- [ ] **M5.2** Parse `-progress pipe:1` key/value records; compute percentage only if duration is known. Treat speed/ETA as estimates.
- [ ] **M5.3** Define task states: Pending, Preparing, Running, Completed, Failed, Cancelled (and legal transitions); keep task models Qt-independent.
- [ ] **M5.4** Implement a sequential task queue first: add, start, cancel, retry, per-task logs, and safe management of partial output files.
- [ ] **M5.5** Add Queue view with progress, output path, status, logs, and errors; run crash/forced-stop scenarios.
- [ ] **M5.6** Extend to bounded parallelism only after serial execution and GPU contention behavior are tested.

**Acceptance:** a long operation does not freeze the UI; it can be cancelled safely; no failed or partial output is presented as complete; other queued jobs continue according to policy.

## Milestone 6 — Transcoding and compression (P1)

- [ ] **M6.1** Add Convert page: output container, video encoder, audio encoder, stream mapping, resolution and FPS, and copy-vs-encode decisions for each stream type.
- [ ] **M6.2** Add Compress page: quality-oriented mode (codec-appropriate CRF/CQ), bitrate mode, preset/speed, audio quality, and clear size/quality tradeoff labels.
- [ ] **M6.3** Add optional target-file-size mode with video-bitrate calculation and two-pass support when the selected encoder/mode supports it; do not promise exact sizes.
- [ ] **M6.4** Build presets for common goals (e.g., quality-oriented H.264 MP4, efficient H.265, audio-only). Keep presets editable.
- [ ] **M6.5** Test remux-vs-transcode behavior, quality options per encoder, audio stream handling, incompatible containers, and failed encodes.

**Acceptance:** CPU transcoding and compression work end-to-end with command preview, logging, progress, and output verification.

## Milestone 7 — CPU/GPU capability detection and selection (P1)

- [ ] **M7.1** Enumerate FFmpeg version/build, `-encoders`, `-hwaccels`, and selected encoder help; cache results by executable identity/version.
- [ ] **M7.2** Distinguish encoder *listed by build* from *runtime-tested working* and *unavailable/unknown*; account for driver/device limitations.
- [ ] **M7.3** Add optional short runtime encode smoke test using synthetic media for candidates such as NVENC, QSV, AMF, VAAPI (only where supported).
- [ ] **M7.4** Present CPU / GPU / Auto; expose actual encoder and capabilities. Never assume that a named GPU makes an encoder work.
- [ ] **M7.5** Handle failed GPU initialization with actionable diagnostics and an opt-in/clearly described CPU fallback without overwriting partial outputs.
- [ ] **M7.6** Test no-GPU, multiple encoder candidates, changing FFmpeg binary, and runtime smoke-test failure; document hardware coverage.

**Acceptance:** no unsupported encoder is silently advertised as usable; hardware acceleration is selectable when actually supported, while CPU always remains a valid path for supported operations.

## Milestone 8 — Advanced user workflows (P2)

- [ ] **M8.1** Save/import/export versioned profiles; profiles must validate against the current FFmpeg build.
- [ ] **M8.2** Batch add and per-file output naming templates with collision detection.
- [ ] **M8.3** Explicit advanced stream mapping, subtitle handling, metadata and chapter preservation policies.
- [ ] **M8.4** Configurable logging / diagnostics export with safe handling of file paths and privacy-sensitive metadata.
- [ ] **M8.5** Optional custom arguments as a tightly scoped advanced feature: preview and validate; never allow overriding output safety or shell execution protections.
- [ ] **M8.6** Optional resumable queue definitions (not mid-encode FFmpeg checkpointing); revalidate files/settings after restart.

**Acceptance:** advanced workflows are reproducible and do not bypass validation or output safety.

## Milestone 9 — Cross-platform distribution, verification and release (P1 before public release)

- [ ] **M9.1** Support both binary modes: bundled sidecar binaries and user-selectable external paths/PATH. Show active FFmpeg/FFprobe paths and versions.
- [ ] **M9.2** Produce reproducible Windows and Linux distribution builds, including Qt runtime dependencies, icons, and documentation.
- [ ] **M9.3** Test clean installs and removals on Windows and Linux; verify spaces/Unicode paths, permissions, long paths where relevant, and media files in read-only directories.
- [ ] **M9.4** Document bundled binary origins, licenses, build configuration, redistribution obligations, and third-party notices. Do not bundle binaries until compliance is reviewed.
- [ ] **M9.5** CI: unit tests + lint on Linux/Windows; integration tests using small fixtures; manual GPU test matrix by available hardware.
- [ ] **M9.6** Release notes, known limitations, troubleshooting, and tagged version.

**Acceptance:** user can install, inspect and run remux/transcode/compress on both supported OSes; installer/bundle and limitations documented.

## Dependency/order guidance

Suggested execution slices:

1. **M0 -> M1 shell -> M2 inspection** (stabilize the current prototype).
2. **M3 -> M5.1/M5.2 -> M4** (first genuine end-to-end remux operation).
3. **M5.3–M5.5 -> M6** (queue plus transcoding/compression).
4. **M7 -> M8** (GPU selection and advanced workflows).
5. **M9** starts early with CI/binary resolution; finish packaging at release.

**Do not implement all milestones in one agent run.** Pick the first incomplete task, make a focused change, run relevant tests, report results, and propose the next task.

## Initial Codex assignment

> Read `AGENTS.md`, `docs/ARCHITECTURE.md`, and this roadmap. Audit the existing source and tests. Complete **M0.1–M0.2 only**: report implemented functionality, run tests and the app where available, identify blockers, and propose the smallest concrete next code change. Do not implement remux or redesign the UI yet. Update only verified roadmap checkboxes. Include exact commands and outcomes in your final report.
