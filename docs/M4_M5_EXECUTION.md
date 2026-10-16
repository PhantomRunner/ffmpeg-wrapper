# M4/M5 execution verification

Linux verification only; Windows native/hosted CI remains pending.

## M5.1
Single-use QProcess runner separates stdout/stderr, reports start/exit/crash errors once, bounds diagnostics, and supports terminate then timed kill without blocking. Ten targeted runner/UI tests and Ruff pass, including cancellation responsiveness and crash handling.

## M5.2
Incremental bounded progress parser connected to runner signals: microseconds, known-duration percentage, estimated speed/ETA, unknown and malformed values. End progress is not task success. Eight targeted tests and Ruff pass.

## M5.3
Qt-independent task record and explicit legal Pending/Preparing/Running/Completed/Failed/Cancelled transitions; bounded per-task logs and progress/results. All 36 transition pairs plus identity/log isolation tested (37 pass); Ruff passes.

## M4.1
Remux now exposes real-index track checkboxes synchronized with Inspect. Selected indices flow through preparation; changing selection invalidates preview. Updated UI fixture to use inspected state. 217 tests pass; Ruff passes.

## M4.2
Selected-stream compatibility checked inline and again in worker preparation. Unsupported tracks stay selected and block Run with their index/codec; user must explicitly deselect. Empty selection blocks execution. 30 shell/remux tests and Ruff pass.

## M4.3
Remux uses shared runner and adjacent temporary output. Worker re-probes input and verifies output stream kinds/codecs/count and nonempty size. Atomic hard-link publication refuses existing destinations; unsupported filesystems fail safely and retain partial output. Cancel waits for process/worker cleanup; publication is the commit point. 221 tests and Ruff pass, including real staged Remux, preparation cancellation and publication collision. No automatic partial deletion.

## M4.4
Remux displays actual executed arguments (including generated temporary target), cancellation control, progress estimates, final result path and verified metadata. Preview explains regeneration of temporary path on Run. Twenty shell/UI tests and Ruff pass, including visible verified PCM output and executed progress arguments.

## M4.5
226 tests and Ruff pass. Real generated multi-track source verifies chosen-track copy and output codec/count; incompatible MP4 selection fails without output. Tests exercise failure exit, cancellation during running, zero-exit invalid output, and a final destination created at publication time. Partials retained, no false completion, no overwrites.

## M5.4
Sequential queue snapshots plans/binaries, supports pending/active cancellation and fresh-attempt retry, retains history/logs/partial paths, and continues after failure or cancellation. Ten queue/task tests pass with real FFmpeg; at most one preparing/running task is asserted. Ruff passes.

## M5.5
Queue page shows source/output, status, progress, estimated speed/ETA, actual arguments, verified metadata, bounded per-task diagnostics, errors and partial paths. Remux can enqueue snapshots; Start/Cancel selected/Cancel all/Retry controls are wired. Busy guards prevent overlapping standalone work and premature window destruction. Tests exercise real queue UI failure/completion/cancel/retry, crash isolation and stubborn-process forced kill. 232 tests, Ruff and whitespace checks pass. Remux and Queue visually reviewed offscreen at 900x650.

## Remaining limits and next task
M4.1–M4.5 and M5.1–M5.5 are locally verified. M5.6 remains unchecked:
serial behavior is tested, but GPU operations/capability discovery are not yet
implemented (M7), and no GPU contention verification is available. Parallel
execution would violate its explicit prerequisite. The queue is intentionally
sequential, session-only, and does not resume after application/OS crashes.
A crash can leave a hidden `.partial.mkv`/`.partial.mp4` beside the destination;
files are never automatically deleted. Diagnostics retain the last 16000
characters per task; application errors also go to the rotating diagnostic log.

Publication uses an atomic hard link on the destination filesystem, then removes
only the temporary link. Filesystems without hard links fail safely and retain
the verified temporary file; there is no overwriting rename fallback. A cleanup
failure after publication is reported as a warning, with both paths retained.
Cancellation accepted before publication prevents completion; after the atomic
publication commit point, successful publication is reported as completed.
Verification checks selected stream kinds/codecs/count and nonzero size, not
bitwise packet equivalence. Metadata/chapter policy remains M8.3.

Windows native execution and hosted Linux/Windows CI remain unavailable (M0.4).
Next independent roadmap task: M6.1 Convert UI; revisit M5.6 after M7 and GPU
contention tests. No GPU encoder is offered or silently selected by this change.
