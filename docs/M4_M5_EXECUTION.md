# M4/M5 execution verification

Linux verification only; Windows native/hosted CI remains pending.

## M5.1
Single-use QProcess runner separates stdout/stderr, reports start/exit/crash errors once, bounds diagnostics, and supports terminate then timed kill without blocking. Ten targeted runner/UI tests and Ruff pass, including cancellation responsiveness and crash handling.
