# M0.3 — Errors, diagnostics, annotations and configuration location

Completed on Linux, 2026-10-16. Scope is the existing Detect / Inspect / Remux flow.

## Behavior

Application services now expose ApplicationError for failures, preserving causes.
Missing files, permissions, timeout, malformed JSON and validation failures have
consistent recovery messages. Unexpected exception details stay in diagnostics.
Workers log once before emitting failure; RemuxTask also reports preflight, start
and process-exit failures through this path. Controls recover after each failure.
QProcess diagnostics include the exit code/status and existing bounded output tail.

Startup resolves native per-user config/data locations through QStandardPaths with
application name MediaWrapper. AppPaths uses pathlib throughout. settings.json is
reserved for later preferences work and is not created now. The status bar shows
the actual log path or an explicit file-logging failure and stderr fallback.
Rotating UTF-8 logs use a QueueListener, drain on normal shutdown, and keep three
backups. Logger handlers are removed/closed on shutdown. Existing logs are appended,
not truncated. Logs contain local paths and diagnostic details; the README explains
where to find them and the stderr fallback.

All source functions now have explicit argument/return annotations. MediaInfo's
numeric helper preserves its int/float return type; no parser semantics changed.
The domain remains Qt-independent; UI invokes application services, and infrastructure
owns process and native path operations. No new dependencies or UI framework.

## Verification

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check . --no-cache
git diff --check
```

**Results: 51 tests passed (no skips); Ruff and whitespace checks passed.**
The suite covers the existing remux/Inspect integration plus:

- Application error translation, causal chains, subprocess stderr retention,
  known and unexpected failures, and one diagnostic record per worker failure.
- Qt native location selection, missing-location errors and no settings-file creation.
- UTF-8 append behavior, asynchronous writes, log rotation and listener flush/cleanup.
- Unusable log directory and absent path fallbacks without changing existing files.
- Asynchronous UI recovery after detection, inspection, preparation, process-start
  and nonzero process-exit failures; logged backend details and visible recovery text.
- Real entry-point startup and graceful close in isolated temporary locations,
  both with normal file logging and with stderr fallback.

Linux tests use offscreen Qt. Native dialog interaction, Windows execution and
Python 3.11 runtime verification remain unavailable; Windows path selection delegates
to Qt and is not presented as a tested Windows installation. No persistence, cancellation,
queue, capability detection or further remux feature was added. Runtime disk failures
are handled by the standard logging handler's stderr diagnostics; the status-bar
fallback notification covers initialization failures.

## Next task

M0.4: baseline binary-resolution / FFprobe / path error tests and Linux/Windows CI.
The baseline audit's parser, stream-label, builder-validation and runner lifecycle
findings remain open for their assigned tasks. The original audit is historical;
its missing-logging and missing-annotations finding is addressed here.
