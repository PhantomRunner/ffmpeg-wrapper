# M6 encoding verification

Linux only; native Windows and hosted CI remain pending.

## M6.1
Convert form offers per-track copy/omit/CPU encoding, container/output, resolution and rational FPS. Worker discovers encoders from the selected build before preview/execution; common queue handles progress/cancel and verified publication. Output verification checks encoded codecs, resolution and FPS. Qt shutdown lifetime corrected with bound slots and deferred deletion before teardown. 238 tests and Ruff pass, including real FFV1/PCM to scaled H.264/AAC and startup shutdown.

## M6.2 implementation
Compress form adds CRF/bitrate, encoder preset and AAC bitrate/quality controls.
Conflicts are rejected in domain policy. Milestone-wide verification pending.
