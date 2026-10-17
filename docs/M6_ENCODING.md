# M6 encoding verification

Linux only; native Windows and hosted CI remain pending.

## M6.1
Convert form offers per-track copy/omit/CPU encoding, container/output, resolution and rational FPS. Worker discovers encoders from the selected build before preview/execution; common queue handles progress/cancel and verified publication. Output verification checks encoded codecs, resolution and FPS. Qt shutdown lifetime corrected with bound slots and deferred deletion before teardown. 238 tests and Ruff pass, including real FFV1/PCM to scaled H.264/AAC and startup shutdown.

## M6.2 implementation
Compress form adds CRF/bitrate, encoder preset and AAC bitrate/quality controls.
Conflicts are rejected in domain policy. Milestone-wide verification pending.

## M6.3 implementation
Target-size mode estimates video bitrate after known audio rates and 2% muxing
reserve. Supports one libx264 video, requires known duration and known-rate audio,
and runs two passes. Both commands are previewed; pass logs are private per
attempt, cleaned on success and retained/reported on failure. No exact-size claim.
Milestone-wide verification pending.
