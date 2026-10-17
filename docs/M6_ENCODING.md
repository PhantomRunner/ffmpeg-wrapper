# M6 encoding verification

Linux only; native Windows and hosted CI remain pending.

## M6.1
Convert form offers per-track copy/omit/CPU encoding, container/output, resolution and rational FPS. Worker discovers encoders from the selected build before preview/execution; common queue handles progress/cancel and verified publication. Output verification checks encoded codecs, resolution and FPS. Qt shutdown lifetime corrected with bound slots and deferred deletion before teardown. 238 tests and Ruff pass, including real FFV1/PCM to scaled H.264/AAC and startup shutdown.

## M6.2 implementation
Compress form adds CRF/bitrate, encoder preset and AAC bitrate/quality controls.
Conflicts are rejected in domain policy. Verified by the milestone-wide checks below.

## M6.3 implementation
Target-size mode estimates video bitrate after known audio rates and 2% muxing
reserve. Supports one libx264 video, requires known duration and known-rate audio,
and runs two passes. Both commands are previewed; pass logs are private per
attempt, cleaned on success and retained/reported on failure. No exact-size claim.
Verified by the milestone-wide checks below.

## M6.4 implementation
Editable H.264 MP4, efficient H.265 MP4 and audio-only AAC MP4 starting points.
Applying a preset populates visible controls; user changes remain editable.
Audio-only explicitly omits non-audio tracks; other presets retain subtitles for
explicit compatibility validation. Verified by the milestone-wide checks below.

## M6.5 milestone-wide verification
257 tests pass (`python -m pytest -q`); Ruff, `pip check` and whitespace checks pass.
Real fixtures cover scaling/FPS, AAC audio, H.264/H.265 quality, bitrate mode,
two-pass H.264 and verified publication. Tests include unavailable encoders,
invalid/conflicting options, incompatible copy/container, failed encode without
publication, editable presets and preview-to-queue UI execution. Startup/shutdown,
inspection, Remux, queue and cancellation regression tests pass. Offscreen Compress
layout reviewed at 900x650; the form scrolls to advanced controls and actions.

Target size supports one libx264 video plus audio with known bitrate; it reserves
2% for muxing and never guarantees an exact file size. Exact dimensions are used
(no implicit aspect-ratio policy). CPU encoders are checked against the selected
build before execution. Pass logs are isolated per attempt, removed on success
and retained with their location in diagnostics on failure. Windows and GPU
execution are not claimed. Next: M7 capability discovery and runtime GPU tests.
