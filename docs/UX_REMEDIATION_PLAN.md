# UX remediation plan

Current development plan; [project context](PROJECT_CONTEXT.md) records product
intent. [ROADMAP](ROADMAP.md) remains historical functional/release evidence.
Preserve service boundaries, asynchronous execution and no-overwrite publication.

## Audit (2026-10-18)

| Problem | Root cause in current implementation |
| --- | --- |
| Playback placeholder | `ui/workspace.py` constructs an EmptyState, with no player, video surface, audio output or transport. `panels/media_timeline.py` has static duration lanes but no playback position binding. |
| Navigation changes only settings | `main_window.py` connects currentRowChanged to pages.setCurrentIndex; Workspace always keeps the same three columns and bottom tabs. Queue only selects the processing tab. |
| Convert/Compress similarity | Both are EncodingView; the title/operation changes but the same controls and hierarchy are built. Existing conversion services already support quality/bitrate/target-size modes. |
| Stale extension | Container signals invalidate previews/update state without rewriting destination. Only apply_preset explicitly changes a suffix; source selection creates an initial name. Existing path/policy validators already reject mismatched extensions. |
| Clipped dropdowns | Plain QComboBox instances, including dynamically built stream rows, lack popup content sizing and item tooltips. Global QListView row styling adds padding while popup width remains coupled to compact fields. |
| Limited Remux | Container enum, codec_policy.ALLOWED, validators, batch naming, UI indices/filters and preference/profile/queue schemas assume MKV/MP4. Capability inventory must be checked for muxer support before expanding choices. |

## Ordered tasks and acceptance gates

### U0 — Context, audit and baseline

Save context, link instructions, record root causes, run existing tests before edits.
Add regressions for extension changes, stale previews and retained output safety.
Acceptance: baseline outcome and subsequent checks recorded below; historical
roadmap is preserved. No claim of Windows/release approval from offscreen tests.

### U1 — Output extension synchronization (first implementation slice)

Dependencies: U0. Share a path suggestion helper between Remux/Convert/Compress.
On container change preserve parent and filename stem, replace/add suffix; empty
or malformed paths must not crash. Keep manually typed mismatches visible for
existing validation; clear stale command previews. Update Remux state atomically.
Preset/profile/source/browse behavior must remain usable. Never write/rename files.
Acceptance: regression tests cover both containers, custom/multi-dot/Unicode names,
empty/extensionless paths, all three forms, preview invalidation, mismatched manual
extensions, existing destinations and source collision rejection.

### U2 — Readable dropdowns (second implementation slice)

Dependencies: U0. Shared Qt combo for static and dynamic fields; size popup from
content/delegate metrics and available screen, preserve compact closed controls,
provide full item tooltips, readable rows and scrolling for extreme labels.
Acceptance: show actual themed popups in tests, check content/viewport geometry,
keyboard selection, long labels, dynamic items and screen bounds at 100%/200% Qt
scale. Native Linux/Windows physical-display acceptance remains a separate gate.

### U3 — Operation workspace composition

Dependencies: U1/U2. Introduce explicit mode layouts controlling panel visibility,
proportions, primary actions and timeline context; reuse instances/services. Inspect
emphasizes preview/metadata/media timeline; operations emphasize their controls;
Queue emphasizes processing; Settings emphasizes configuration. Persist per-mode
splitters with versioned migration/reset. Avoid destroying state on navigation.
Acceptance: switch all modes with selected media and active jobs; preserve stream
choices, edited forms, selection, progress, keyboard reachability and layout restore.

### U4 — Separate Convert and Compress workflows

Dependencies: U3. Reuse request generation/services with distinct control hierarchy:
Convert container/codecs/streams/resolution/FPS; Compress quality/bitrate/target size,
preset and estimates using existing target-size policy. Keep advanced controls.
Acceptance: equivalent requests retain commands/safety; mode changes update enabled
controls and estimates; unsupported combinations produce actionable validation.

### U5 — Real playback and Media Timeline synchronization

Dependencies: U3 (U4 precedes implementation). Evaluate QtMultimedia from existing
PySide6 dependency with a playback adapter and explicit platform/backend fallback.
Add play/pause, seek, position/duration, audio/video handling and error presentation.
Synchronize the read-only Media Timeline; processing progress remains independent.
Acceptance: real audio/video fixtures, pause/resume/seek/source switch/end/error,
missing/unsupported media and shutdown; responsive UI during jobs; native Linux
and Windows backend/packaging verification. No export-range editing in this task.

### U6 — Extensible validated Remux containers

Dependencies: U1/U4; follows U5. Inventory all enum assumptions, add domain registry
(muxer, extensions, stream policy) and selected-build muxer discovery in infrastructure.
Choose conservative additional formats after validation evidence; migrate persisted
schemas without breaking MKV/MP4 profiles/queues/preferences. No blanket codec allow.
Acceptance: per-container command/mapping/extension/compatibility tests, unavailable
muxer rejection, real fixture remux/probe and no-overwrite publication regressions.

### U7 — Visual polish and release verification

Dependencies: U1–U6. Apply remaining design tokens/hierarchy only after usability is
verified. Exercise native Linux/Windows, small screens, DPI, keyboard, playback and
packaged builds. Existing release/GPU/license gates remain open until evidenced.

## Verification log

Implementation and local checks for U0–U2 are recorded here as they run. U3–U7 are
planned, not implemented. Physical-display and Windows acceptance are pending.

### U0/U1/U2 local implementation evidence — 2026-10-18

- Baseline before code changes: `python -m pytest -q` — **351 passed**.
- Context saved in PROJECT_CONTEXT.md; AGENTS.md now requires reading context and
  this plan before UI work. ROADMAP.md was left unchanged.
- U1 implemented: shared suggestion helper changes only the suffix; Remux updates
  model path/container in one call, encoding forms use the same helper, and presets
  retain explicit resynchronization. Manual edits are not silently normalized.
  Existing path/plan validation and execution/publication code are unchanged.
- U2 implemented: ReadableComboBox used in Remux, Settings, encoding controls and
  dynamic stream rows. Popup width uses styled delegate metrics and available
  screen geometry, with item tooltips and horizontal scrolling for extreme labels.
  QComboBox resets scrollbar policy on opening; the component restores it afterward.
- Added 13 regressions in `tests/test_ux_remediation.py`: suggestion edge cases,
  three-form updates and preview invalidation, source/existing-output safety,
  manual extension rejection, actual themed popup viewport/screen geometry,
  dynamic long items, tooltips, scrolling and keyboard selection.
- Targeted tests: **13 passed** at default scale and **13 passed** with
  `QT_SCALE_FACTOR=2`; Qt offscreen platform. Changed Python files pass Ruff;
  `git diff --check` passes.
- U1/U2 implementation is verified locally by widget and service tests. Native
  Windows and physical Linux/Windows visual/DPI acceptance remain **pending**;
  offscreen geometry tests do not establish physical-display correctness.
- Next focused implementation task: **U3**, operation-specific workspace composition,
  with state-preservation tests before changing navigation. U3–U7 remain unimplemented.
- Final complete regression suite after all additions: **364 passed** in 26.87 s,
  including existing real FFmpeg integration tests.

### U3 — operation workspace composition

Implemented operation-level visibility/proportions and timeline defaults. Queue
occupies the main area; Settings hides media panels; Remux uses Library + controls;
Inspect defaults to Media Timeline. Existing instances retain edits and selection.
Layout version 2 stores each mode separately and reads version 1 without changing
JSON preferences. Reset affects the current mode. Local verification: 364 existing
tests passed; the added navigation test initially compared tuple to set, corrected
without production changes; all 3 workspace tests then passed. Native display and
Windows acceptance remain pending.
