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
