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

Known limitations: conservative MP4/Matroska codec support; target size is an
estimate; no parallel queue or mid-encode resume; metadata support varies by
container. Native Windows, physical GPU success, real-desktop distribution checks
and dependency/license release approval remain pending. No FFmpeg binary ships
with the candidate. No public release tag has been created.

Release status: candidate only. The package metadata remains 0.1.0 for continuity;
a version tag is deliberately deferred until the release checklist is satisfied.
Portable installation/removal and recovery guidance: docs/DISTRIBUTION.md.
Exact native/hardware verification status: docs/RELEASE_CHECKLIST.md.
