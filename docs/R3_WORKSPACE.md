# R3 — Workspace shell

Implementation verified on Linux, 2026-10-18. Toolbar, horizontal mode navigation,
three-panel horizontal splitter and vertical timeline splitter now compose the
existing controls. Library remains visible; metadata and operations occupy the
Inspector; queue controls live below. The preview explicitly states that playback
is unavailable. No existing operation/service was removed.

Layout version 1 uses a separate QSettings store composed in main.py. Splitter
state, active mode and timeline tab survive restarts; corrupt/missing state falls
back to defaults. Reset layout restores proportions. Tests inject a temporary INI
store; existing JSON preferences remain independent. Native dialogs are retained.

Validation: 341 pytest tests passed; Ruff and diff checks passed. Real local
FFmpeg detection, generated WAV inspection and pending Remux enqueue exercised
all six modes at 960×640, 1280×720 and 1920×1080 at scale factors 1 and 2 using Qt
offscreen. Navigation/persistence tests verify reopen, reset and corrupt values.
Windows native rendering/restart verification remains open for R6; R3's full
cross-platform acceptance is not claimed until that is run.

Next: R4 model-backed Library, contextual Inspector and validated queue snapshots.
