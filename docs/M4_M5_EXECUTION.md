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
