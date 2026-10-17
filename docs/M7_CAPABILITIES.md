# M7 capability verification

Linux development; native Windows and GPU hardware execution coverage will be recorded at the milestone boundary.

## M7.1 implementation
Selected executable version/build configuration, encoders, hardware APIs and help
for supported encoder candidates are queried on workers. Immutable inventory is
cached in memory by resolved executable path, size, modification time and version;
refresh bypasses cache. No GPU runtime availability is inferred from these lists.
Verified by the milestone-wide checks below.

## M7.2 implementation
Reports distinguish listed/untested, runtime-tested, unavailable and unknown.
Hardware API/encoder listing alone never grants runnable GPU status. Reports are
immutable snapshots; rescanning resets runtime evidence rather than reusing stale
device results. Verified by the milestone-wide checks below.

## M7.3 implementation
Optional worker-based NVENC/QSV/AMF/VAAPI synthetic encode tests have a 15-second
per-candidate timeout and cancellation/reaping. Output goes to the null muxer;
no user media or output is touched. VAAPI requires an explicit render device.
Unknown/failed tests never become runnable claims. Verified by the milestone-wide checks below.

## M7.4 implementation
Settings offers asynchronous scan/refresh, opt-in runtime tests, explicit VAAPI
render-device selection, cancellation and build/help/runtime diagnostics. Convert
and Compress offer CPU/GPU/Auto; only runtime-tested candidates appear as GPU
choices. Auto chooses a tested matching codec or explicitly records CPU choice.
GPU default/bitrate modes are supported; CRF/target size stays CPU in Auto and is
rejected in forced GPU mode. Execution rechecks GPU initialization before media
encoding. VAAPI uses the explicit device and software-to-hardware upload filter.
Verified by the milestone-wide checks below.

## M7.5 implementation
Failed GPU preflight/execution never silently restarts on CPU. Queue offers an
explicit Retry on CPU action only for failed/cancelled GPU attempts. It snapshots
a fresh CPU plan and temporary target, retaining the prior attempt/log/partial.
CPU encoder availability and destination safety are revalidated. Milestone-wide
tests pending.

## M7.6 milestone-wide verification
270 tests pass (`python -m pytest -q`); Ruff, dependency integrity (`pip check`)
and whitespace checks pass. Regression coverage includes M0–M6 startup/shutdown,
Inspect, Remux, CPU compression, two-pass execution, output safety and queues.
Tests exercise per-build cache invalidation, no-GPU states, multiple simulated
working candidates, explicit candidate selection, timeout/failure/cancellation,
VAAPI device/upload arguments, UI scan cancellation, binary-change invalidation,
and explicit GPU-to-CPU retry preserving logs and existing partial output.
A Qt worker attribute shadowing QObject.event was caught and corrected during
UI verification. Capability text is refreshed only when its report changes.
Settings was visually reviewed at 900x650 after an actual worker-based GPU scan.

### Hardware coverage
Actual local FFmpeg n9.0.2 reports 226 encoders and hardware APIs including CUDA,
QSV, VAAPI and AMF. Short real smoke tests produced these results:
- H.264/HEVC NVENC: unavailable, CUDA_ERROR_NO_DEVICE.
- H.264/HEVC QSV: unavailable, MFX session initialization error -9.
- H.264/HEVC AMF: unavailable, libamfrt64.so.1 could not be loaded.
- H.264/HEVC VAAPI: unknown; no /dev/dri render device was present to select/test.
No GPU encoder was advertised as runtime working in this environment. Successful
GPU selection/failure recovery paths use simulated evidence in tests; successful
physical NVENC/QSV/AMF/VAAPI output and native Windows execution remain unverified.
Runtime reports are session snapshots, not guarantees for every resolution,
profile or driver state. Execution re-tests selected GPU initialization and still
reports actual job failures; it never silently falls back.

### Scope and next work
GPU mode supports H.264/HEVC default or bitrate control. Auto keeps CRF and target
size on CPU; forced GPU rejects those options. VAAPI uses the explicitly tested
render node. Other backends use the driver's default device; per-adapter selection
and GPU-specific quality controls are outside this slice. CPU retry is opt-in,
creates a new attempt, and may fail if the selected build lacks its software
encoder. Reports/cache are in memory; refresh rechecks build and device behavior.
M5.6 remains open because physical GPU contention testing was unavailable.
Next independent task: M8.1 versioned profile save/import/export.
