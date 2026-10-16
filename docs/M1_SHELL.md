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
