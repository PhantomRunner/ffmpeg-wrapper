# M1 application shell verification

## M1.1
Independent Files/Inspect, Remux and Settings pages plus labeled Convert/Compress/
Queue placeholders. Navigation preserves current activity output and existing
operations. `pytest -q`: 76 passed on Linux offscreen; Ruff passed.
Windows/native desktop verification remains pending.

## M1.2
DesktopState and DesktopViewModel own operation state and asynchronous coordination;
workers invoke application services. MainWindow binds pages and presents state.
Repeated requests while busy are rejected; navigation remains available.
77 tests pass, including a held-worker responsiveness/concurrent-request check;
Ruff passes. Existing real Inspect/Remux and failure recovery tests remain green.

## M1.3
Multi-file picker, validated/deduplicated local-file list and drag/drop, explicit
current-file inspection, clear-files action and recent output directory. Changing
selection invalidates the inspected source to prevent remuxing a stale file.
Invalid mixed additions are rejected without silently dropping entries. Busy
operations prevent file-list mutation. Batch inspection remains M2 work.
83 tests pass (including picker, drop rejection, stale state and recent directory);
Ruff passes. Native dialogs on Windows remain untested.

## M1.4
Remux Output group contains destination, container, browse, inline validation and
Run. Advanced details has a read-only JSON argument-array preview built by the
application service in a worker. Inputs invalidate previews; Run probes/validates
again, including destinations created after preview. Tooltips explain binary
selection, stream copy and overwrite policy. No custom raw arguments were added.
84 tests pass, including preview-without-output, invalid form states and late
output collision; Ruff passes.

## M1.5
Version-1 Qt-independent preferences, application load/save policy and atomic UTF-8
JSON repository. Restores mode/folder before startup detection, container, advanced
view, active page, window size and recent destination. Saves on normal close.
Media selections and jobs remain session-only. Unsupported, malformed and detected
externally edited settings are preserved; failed writes retain the previous file
and clean temporary files. Load warnings are visible; save failures show a dialog.
Native config directory comes from the M0.3 path adapter. No new dependencies.

107 tests passed on Linux; Ruff passed. Coverage includes schema invalid values,
roundtrip with Unicode, bad/future settings, atomic-write failure, external edits,
read failures, actual entry-point save and two-window restore. An offscreen visual
check inspected generated WAV media, navigated to Remux and displayed the real
argument preview; no output file was created. Files and Remux screenshots were
reviewed. Windows/native-dialog verification remains pending.

## Milestone acceptance
Navigation preserves Inspect and Remux, a held worker does not block navigation,
and all FFmpeg arguments come from the application/infrastructure builder. M1.1–
M1.5 are complete on the available development machine. M0.4's hosted cross-platform
run remains an explicit external prerequisite for claiming M0 fully verified.
Next implementation milestone is M2 (typed inspection models), beginning M2.1.
