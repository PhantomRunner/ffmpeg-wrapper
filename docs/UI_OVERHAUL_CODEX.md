# UI Overhaul — Media Workstation v2

## Objective
Replace the existing PySide6 interface with a professional, dark, Adobe Premiere-inspired **Hybrid** workspace at **Balanced** density. Preserve every completed backend feature and public workflow. This is a UI migration, not a rewrite.

## Source of truth
Before changing code, read `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, and `docs/UI_UX_SPEC.md`. Inspect the actual current repository: the previous roadmap is complete, but never assume exact class names or APIs without checking.

## Non-negotiable constraints
- Keep Python/PySide6 and existing backend, FFmpeg/FFprobe execution, GPU discovery, task queue, profiles, settings, and tests.
- Do not introduce a web UI or a second application framework.
- Never call FFmpeg directly from a widget. Route actions through existing application services/controllers.
- Never block the GUI thread with probing, transcoding, thumbnail generation, or file I/O.
- Preserve external/bundled FFmpeg modes and Linux/Windows compatibility.
- Preserve keyboard navigation, readable contrast, focus states, accessibility labels, high-DPI behavior.
- Make small, reviewable commits; avoid an all-at-once replacement.
- Maintain existing tests and add UI/regression tests where appropriate.

## Target workspace
```
+--------------------------------------------------------------+
| App toolbar: project, import, workspace, settings, status    |
| Modes: Workspace | Convert | Compress | Remux | Queue        |
+-----------------+-------------------------+------------------+
| Media Library   | Source Preview          | Context Inspector|
| files, metadata | playback and controls   | operation config |
|                 |                         | Add to Queue     |
+-----------------+-------------------------+------------------+
| Bottom: [Processing Timeline] [Media Timeline]              |
| resizable timeline / track list / task status               |
+--------------------------------------------------------------+
| Status: FFmpeg binary, encoder, active tasks, notifications |
+--------------------------------------------------------------+
```
Use nested QSplitters, QStackedWidget for modes and timeline switching, QAbstractItemModel for media/tasks. Keep a single source of truth for selection and state. Initial width proportions 23/47/30 and top/bottom 68/32, adjustable and persisted.

## Design tokens (initial)
- Background `#15171C`; panels `#22242B`; controls `#30333C`
- Accent `#A99CF5`; primary text `#ECECF1`; secondary text `#A3A6B2`
- Completed `#419883`; failed: accessible muted red; pending: neutral gray
- Body text 13–14 px, controls 32–36 px high, 8–12 px gaps, 12–16 px panel padding, 4–8 px radii
- Compact professional chrome, no excessive shadows or decorative glass
- Prefer central theme tokens/QSS; use icons and text for state, never color alone.

## Timeline definitions
### Processing Timeline
A task list rendered as horizontal progress tracks, **not** a time ruler. Show file name, operation/codec, percentage when known, status, ETA if available, cancel/retry and details/log access. Use existing queue model and events. Indeterminate progress must be visually distinct; don't fabricate percentages.

### Media Timeline
An actual media-time ruler for the selected source file, with video/audio/subtitle streams as tracks. Initially read-only, backed by FFprobe stream metadata. Seek/playhead may be connected to preview if playback supports it. Do not fabricate waveform data, frame thumbnails, or media duration. No editing features in this migration.

## Migration phases
### R1 — Audit and map existing behavior
- [x] Inventory all windows, views, widgets, models, controllers, signals, shortcuts and backend entry points.
- [x] List existing user workflows and their current UI entry points.
- [x] Identify components to reuse, adapt, or replace.
- [x] Create `docs/UI_MIGRATION_MAP.md` with old -> new mapping and risks.
**Done when:** no existing functionality lacks a destination in the new UI.


R1 evidence: [UI migration map](UI_MIGRATION_MAP.md), 329 tests passed on 2026-10-18.

### R2 — Theme and reusable controls
- [ ] Implement centralized theme tokens and QSS.
- [ ] Create reusable panel headers, action buttons, status labels, empty states and field rows.
- [ ] Validate hover, focus, disabled, error and loading states.
**Done when:** reusable components are demonstrated in the app and old screens remain usable.

### R3 — New workspace shell
- [ ] Build MainWindow toolbar, mode navigation, nested splitters, bottom tab switcher and status bar.
- [ ] Move or wrap existing Media Library, Preview and Inspector without changing backend behavior.
- [ ] Save and restore splitter state and active mode; handle missing/corrupt settings.
- [ ] Support sensible minimum window size and high-DPI displays.
**Done when:** navigation and layout work across restarts on Linux and Windows; existing workflows remain accessible.

### R4 — Contextual Inspector and library
- [ ] Bind selection to one shared state/controller.
- [ ] Display file metadata and stream selection in the Library/Inspector.
- [ ] Provide contextual Convert/Compress/Remux settings by reusing existing validation and profiles.
- [ ] Preserve advanced/expert settings, encoder choice, and FFmpeg command preview if currently available.
- [ ] Wire Add to Queue and action feedback.
**Done when:** all previously supported operations can be configured and queued from the new workspace.

### R5 — Dual timelines
- [ ] Implement Processing Timeline with real queue events and actions.
- [ ] Implement read-only Media Timeline using actual FFprobe stream/duration data.
- [ ] Add accessible switch between timelines; persist selection.
- [ ] Connect selection, seek and preview only where supported.
**Done when:** task progress is accurate and media tracks match probed streams.

### R6 — Preview, polish, regression and rollout
- [ ] Integrate existing preview or show an explicit unsupported-media fallback.
- [ ] Test empty states, huge libraries, long filenames, multiple streams, missing codecs, missing FFmpeg, failures, cancellations and retries.
- [ ] Test keyboard controls, DPI, resizes, Linux/Windows styling and layout restoration.
- [ ] Run existing automated tests and add smoke tests for navigation, task actions and persistence.
- [ ] Remove obsolete screens only after parity is confirmed.
- [ ] Update README/screenshots/docs and mark roadmap items completed with evidence.
**Done when:** feature parity is verified and the new UI is the default.

## Implementation rules for Codex
1. Start with R1 only. Report findings before modifying architecture.
2. Implement one phase or narrow vertical slice at a time.
3. At each phase: show changed files, tests run, results, known gaps and next task.
4. Never mark a checklist item complete unless acceptance criteria are verified.
5. If current repository differs from this document, adapt the migration map instead of overwriting working code.

## First Codex prompt
Read `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/UI_UX_SPEC.md`, and `docs/UI_OVERHAUL_CODEX.md`. The previous functional roadmap is complete. We now want a UI-only migration to the Hybrid Premiere-inspired Media Workstation design. Start with R1: audit the current PySide6 UI, map all existing user-facing features to the new workspace, and write `docs/UI_MIGRATION_MAP.md`. Do not rewrite the backend or start R2 until the audit is finished. Report any feature-parity risks and the recommended first small UI change.
