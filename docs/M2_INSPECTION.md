# M2 robust inspection verification

## M2.1
Immutable Qt-independent MediaFile/MediaStream entities replace raw stream dicts.
Infrastructure translates FFprobe JSON, preserves real indices and optional values,
and parses frame rates as Fraction (average rate with nominal fallback). Invalid
indices/duplicates/shapes fail clearly; absent metadata remains unknown. Existing
Inspect and all-stream Remux use the typed values. 122 tests passed on Linux;
Ruff passed. Windows execution remains pending under M0.4's CI gap.

## M2.2
Inspection now presents container/duration/size/bitrate and a typed stream table:
real index, codec/subtitle type, language, bitrate, frame size, exact rational FPS,
sample rate, channels and layout. Missing values display unknown. Stream checkboxes
store actual indices, with absent indices unselectable; file changes invalidate
selection. The UI explicitly states that this selection is for future operations
and the current Remux slice still copies all streams. 125 tests passed; Ruff passed.

## M2.3
Selected files are inspected sequentially on a Qt worker. Per-file Pending,
Running, Completed, Failed and Cancelled outcomes survive switching the current
file; stream selections are retained per successful inspection. Failures do not
stop other files. Re-inspection invalidates the requested files' cached results.
Cancellation uses a thread-safe event, stops/reaps the active FFprobe process and
marks remaining files cancelled. Successful earlier results remain available.
The worker drains stdout/stderr with short communicate intervals, a 30-second
probe timeout and terminate/kill cleanup on the worker thread. Cancellation is not
an application error and does not produce failure logs. The UI permits navigation
while inspecting and rejects close until cleanup finishes. Remux cancellation is
still deferred to M5.

131 tests pass on Linux, including held-worker UI cancellation/restart, per-file
failure isolation, preserved stream selection, real subprocess cancellation and
timeout/reaping, and large stdout/stderr drainage. Ruff and whitespace checks pass.
Windows process behavior is implemented using portable subprocess APIs but native
execution remains unverified. M2.4's broader fixture coverage is the next task.

## M2.4 and final verification
Generated tiny audio-only PCM, video-only FFV1 and four-track Matroska fixtures
(video, two language-tagged audio tracks and subtitles) verify real FFprobe
results. Exact 30000/1001 frame rates and paths containing spaces/Unicode survive.
An actual Qt-worker batch continues after corrupt media and restores per-file
stream selections. Parser tests cover missing fields and malformed payloads;
service tests cover malformed JSON, unavailable executables, failed processes,
cancellation propagation and the cancellation/failure race. Test configuration
selects the offscreen Qt platform by default, including isolated test runs.

Validation: `.venv/bin/python -m pytest -q` reports 141 passed;
`.venv/bin/ruff check .` and `git diff --check` pass. A 900×650 offscreen
window was visually reviewed with video/audio/subtitle rows: controls and
metadata are visible, with horizontal scrolling for additional stream columns.
No native Windows or hosted CI run was available; M0.4 remains open.
M2 acceptance is satisfied locally. Next: M3.1 typed operation models.
