# R4 — Contextual Inspector and model-backed Library

Implemented 2026-10-18. The Library uses a QAbstractListModel over DesktopState
paths/inspection outcomes. Display uses filenames and explicit status; full paths
and failures remain in tooltips. Status refreshes do not reset selection. Import
and local drop start existing asynchronous inspection; multi-select, explicit
reinspection, cancellation and clear remain available.

Metadata, Remux and both encoding forms use the same selected MediaFile. The
Inspector retains stream maps, preservation, presets, profiles, hardware choices,
restricted arguments and command previews. Advanced encoding and batch controls
are disclosed together; narrow forms wrap labels above fields.

Convert/Compress Add to Queue now calls a small application validation adapter
on the existing ServiceWorker. It reuses inspection, encoder discovery and
prepare_operation to validate a frozen plan before queue insertion. No output is
created or reserved. Execution continues to revalidate. Existing Remux validation
and batch services are retained. FFmpeg services and command building are unchanged.

Validation: full suite 344 tests passed; Ruff and diff checks passed. Added cases
cover a 10,000-file model, shared source identity, asynchronous immutable enqueue,
and refusing existing output. Picker tests now wait for automatic inspection.
Six-mode resize smoke passed at 960×640, 1280×720, 1920×1080 with scale 1 and 2.
Native Windows validation remains pending for the final acceptance matrix.

Next: R5 real processing tracks and metadata-backed media timeline.
