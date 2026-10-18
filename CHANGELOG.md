# Release notes

## Unreleased — 0.1.0 candidate

- Python 3.11+ / PySide6 desktop for Inspect, Remux, Convert and Compress.
- Explicit external/custom/bundled binary selection; current paths and versions.
- Typed command generation, asynchronous sequential queue, cancellation/retry,
  staged output verification and no-overwrite publication.
- CPU encoders and tested GPU selection, quality/bitrate and H.264 target-size modes.
- Versioned profiles, batch naming, stream/subtitle/metadata/chapter controls,
  restricted advanced options, private-by-default diagnostics and queue definitions.
- Native portable build recipe, icon, dependency notices and installation verifier.
- Operation-specific persistent workspace layouts and distinct Convert/Compress forms.
- Timeline panels removed; Queue is standalone, with rounded pane borders and visible resize handles.
- Live approximate output size beside Ready; redundant toolbar Settings action removed.
- Output extension synchronization and screen-bounded readable dropdowns.
- Real audio/video preview with play/pause and slider seeking.
- Registry-based MOV/WebM/WAV/FLAC support with selected-build muxer checks.
- Portable verification now waits for asynchronous enqueue and checks decoded preview.

Known limitations: conservative container/codec support; target size is an
estimate; no parallel queue or mid-encode resume; metadata support varies by
container. Native Windows, physical GPU success, real-desktop distribution checks
and dependency/license release approval remain pending. No FFmpeg/FFprobe processing executable ships
with the candidate; Qt Multimedia preview includes its own media libraries. No public release tag has been created.

Release status: candidate only. The package metadata remains 0.1.0 for continuity;
a version tag is deliberately deferred until the release checklist is satisfied.
Portable installation/removal and recovery guidance: docs/DISTRIBUTION.md.
Exact native/hardware verification status: docs/RELEASE_CHECKLIST.md.
