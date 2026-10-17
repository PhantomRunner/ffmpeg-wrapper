# M7 capability verification

Linux development; native Windows and GPU hardware execution coverage will be recorded at the milestone boundary.

## M7.1 implementation
Selected executable version/build configuration, encoders, hardware APIs and help
for supported encoder candidates are queried on workers. Immutable inventory is
cached in memory by resolved executable path, size, modification time and version;
refresh bypasses cache. No GPU runtime availability is inferred from these lists.
Milestone-wide tests pending.
