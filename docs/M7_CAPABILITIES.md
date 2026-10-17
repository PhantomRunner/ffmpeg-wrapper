# M7 capability verification

Linux development; native Windows and GPU hardware execution coverage will be recorded at the milestone boundary.

## M7.1 implementation
Selected executable version/build configuration, encoders, hardware APIs and help
for supported encoder candidates are queried on workers. Immutable inventory is
cached in memory by resolved executable path, size, modification time and version;
refresh bypasses cache. No GPU runtime availability is inferred from these lists.
Milestone-wide tests pending.

## M7.2 implementation
Reports distinguish listed/untested, runtime-tested, unavailable and unknown.
Hardware API/encoder listing alone never grants runnable GPU status. Reports are
immutable snapshots; rescanning resets runtime evidence rather than reusing stale
device results. Milestone-wide tests pending.

## M7.3 implementation
Optional worker-based NVENC/QSV/AMF/VAAPI synthetic encode tests have a 15-second
per-candidate timeout and cancellation/reaping. Output goes to the null muxer;
no user media or output is touched. VAAPI requires an explicit render device.
Unknown/failed tests never become runnable claims. Milestone-wide tests pending.
