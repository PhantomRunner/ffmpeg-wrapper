# FFmpeg Media Workstation — project context

This is an existing Python 3.11+/PySide6 Qt Widgets application for advanced Linux
and Windows users. The repository is the implementation source of truth. Preserve
the working backend, safety checks and tests; do not restart or rebuild it.
The original functional roadmap is substantially implemented; release verification,
Windows execution and physical GPU/display acceptance remain unfinished.

## Product and design direction

Core capabilities: FFprobe inspection, remux, video/audio conversion, compression,
CPU/GPU encoding, stream mapping, batch/queue processing, profiles, advanced options,
and explicit external/custom/bundled FFmpeg configuration.

Use a Hybrid Adobe Premiere-inspired professional dark workspace: balanced density,
compact readable controls, purple accents, minimal clutter, resizable persistent
panels and context-sensitive layouts. This is a media workstation, not a full editor.
Design tokens: background #15171C, panels #22242B, raised controls #30333C,
accent #A99CF5, primary text #ECECF1, secondary text #A3A6B2. Use system fonts,
approximately 13–14 px body text, 32–36 px controls, 8–12 px spacing and modest radii.

## Workspace intent

Inspect, Remux, Convert, Compress, Queue and Settings share an application shell.
Navigation must change the relevant workspace composition, not only the Inspector.
Reuse Media Library, Source Preview, Inspector/Settings, timelines and Status Bar.
Use QSplitter, QStackedWidget and Qt model/view components where appropriate.

Processing Timeline represents queued/running jobs: completion, status, speed, ETA,
errors, cancel, retry and details. Its bars represent processing completion.
Media Timeline represents actual video/audio/subtitle streams on a media time axis,
synchronized with playback. Initially it is inspection/navigation only; export-range
editing is future scope.

Convert prioritizes container, codecs, streams, resolution and FPS. Compress
prioritizes quality, bitrate, target size, presets and estimated output size.

## Current UX remediation

1. Replace the nonfunctional preview with playback: play/pause, seek, duration,
   position, source lifecycle and actionable errors.
2. Make navigation control the complete workspace while reusing shared components.
3. Separate Convert and Compress workflows.
4. Synchronize output extensions when the container changes; reject incompatible
   manually entered extensions and retain all overwrite/source protections.
5. Fix combo popup geometry, long-label readability, tooltips and DPI scaling.
6. Expand Remux through an extensible container registry, selected-build muxer
   availability and conservative stream compatibility validation.

## Constraints and development workflow

Keep domain Qt-independent, UI bound to application services, and subprocess/OS
work in infrastructure. Widgets must never build or execute FFmpeg commands.
Use argument arrays, never shell=True; keep long operations off the Qt event loop.
Never silently overwrite source/destination files. Keep pathlib and cross-platform
behavior, reuse models/services/tests, and avoid unnecessary dependencies.

Read AGENTS.md, ARCHITECTURE.md, ROADMAP.md and relevant source before substantial
work. ROADMAP.md retains implementation history; UX_REMEDIATION_PLAN.md is the
current development plan. Audit root causes and dependencies, add regression tests,
then implement focused tasks in this order: extensions and dropdowns, workspace
navigation, Convert/Compress separation, playback, expanded Remux. Verify behavior
and update documentation after each task. Do not mark unverified work complete or
attempt a full redesign in one pass. Usability and cohesive architecture precede
final visual polish.
