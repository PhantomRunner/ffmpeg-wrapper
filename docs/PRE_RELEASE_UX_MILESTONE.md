# FFmpeg UI Wrapper — Pre-release UX Milestone

**Status:** Proposed / not implemented.  
**Scope:** Usability and release-blocking workflows before beta/stable release.  
**Platform:** PySide6 Qt Widgets, Linux AppImage and Windows EXE installer.  
**Reference:** Existing `AGENTS.md`, `docs/ARCHITECTURE.md`, roadmap, UI specification and working code are the source of truth; audit actual implementation first.

## Goal
Make the existing workflow predictable and understandable for both new and advanced users without replacing validated FFmpeg infrastructure. Each operation should clearly communicate (1) what will happen, (2) which files are ready or blocked, and (3) what happened after execution.

## P0 — UX-01: Bulk editor (batch parameter editing)

**User story:** Select multiple imported media files and change common operation parameters once instead of configuring each file individually.

### Requirements
- Allow multi-selection in Media Library and open a dedicated **Bulk Edit** surface for Remux, Convert, and Compress where the current domain model supports each operation.
- Support applicable shared settings such as output container, video/audio encoder, preset, quality/bitrate, resolution, stream handling, output directory and filename template. Expose only options supported by the selected operation.
- Show a selected-file count, file list, and pre-apply summary.
- Handle mixed values explicitly (`Mixed` / `Various`), distinguish **unchanged** from **set for all**, and do not silently replace existing per-file overrides.
- Apply changes only to explicitly selected fields. Keep per-file stream selection/compatibility separate when stream layouts differ.
- Validate candidate settings for *each* file before queueing. Incompatible files remain blocked with specific explanations; do not silently skip streams or force unsupported configurations.
- Define persistence semantics: queued jobs are immutable snapshots and are not retroactively changed by bulk edits.
- Use safe output naming: synchronize suggested extensions with container, check conflicts (within batch, existing files, source paths), and never overwrite silently.
- Batch editing is a UI/application-layer orchestration feature; existing typed operation models and validators remain authoritative.

### Acceptance tests
- Selecting 5 files, setting codec once, applies only that explicitly changed field to the selected 5 files.
- Mixed existing values are shown without converting them all to a default merely by opening Bulk Edit.
- Batch of mixed audio/video files receives individual validation; failures show exact reasons.
- Output filename collisions are detected before processing; prior queued task snapshots remain unchanged.

## P0 — UX-02: Contextual parameter help

**User story:** Every relevant processing parameter tells the user what it means, how it affects quality, size, compatibility, speed, and when to use it.

### Requirements
- Add a consistent help affordance near relevant fields (e.g., accessible `?`/info icon with tooltip and optional expanded help text).
- Cover codec/container, CRF/CQ, bitrate, target size, encoder preset, resolution, FPS, hardware acceleration, audio encoding, stream copy/mapping and output naming.
- Help must explain **definition**, **impact**, **recommended use**, and **tradeoffs/limitations** in plain language. Distinguish estimated results from guarantees.
- Make help keyboard-accessible and readable; do not rely on hover alone. Ensure popups and dropdowns do not clip text or extend beyond screens.
- Where encoder-specific ranges or meanings differ, populate help from validated capabilities rather than a misleading universal statement.

### Acceptance tests
- Every primary field in Convert/Compress/Remux has usable contextual help.
- Tooltips/panels remain readable at 1280x720 and high-DPI; Tab navigation and keyboard focus work.

## P0 — UX-03: Validate & Preview actionable feedback

**User story:** Clicking **Validate & Preview** tells the user exactly which inputs are ready, which are blocked, why, and what will run.

### Requirements
- Render a high-visibility validation summary with counts: **Ready**, **Warnings**, **Blocked**; support one-file and batch use.
- Render per-file results with status, output path/container, selected streams, operation/encoders, and concise readable explanation.
- For errors: specify the affected file, field or stream, cause, and an actionable fix (where possible). Examples: incompatible subtitle codec with MP4, missing encoder, collision, no output destination.
- Show a read-only FFmpeg command preview as an advanced disclosure, without making the command string the primary feedback.
- Include explicit, accessible success confirmation for ready files (not only absence of errors).
- Queue/Run action must not allow blocked jobs to start. Distinguish warnings from errors; make handling partial batches explicit (e.g., "Queue 4 ready files, 1 blocked" requiring clear user intent).
- Revalidate when input data/options, capabilities, or paths change. Do not present stale validation as current. Protect against asynchronous/out-of-order validation results.

### Acceptance tests
- All-valid batch shows positive status for each file and clear ready count.
- Mixed batch shows error and resolution advice per failed file; invalid items are not queued.
- Changes to the container invalidate old validation state until refreshed.
- Keyboard and screen reader-friendly text/status semantics are available.

## P0 — UX-04: Prominent operation feedback

**User story:** When the application starts, completes, fails, or cancels an operation, the result is immediately noticeable and understandable.

### Requirements
- Introduce a consistent feedback area (e.g., visible status banner near the workspace action area + task notifications + queue status).
- Important state transitions: validation ready/blocked, added to queue, started, progress, completed, failed, cancelled, output verification.
- On change, visibly update message and icon using text and status (never color alone); where appropriate provide `View details`, `Open output`, `Go to Queue` actions.
- Make progress persistent in the Queue/Processing Timeline, including per-file status. Use transient notifications only as a supplement, not as the sole record.
- Errors remain visible until acknowledged or resolved; successful confirmations can dismiss automatically **only if** detailed results remain accessible.
- Do not show false success before output verification. Prevent duplicate notifications from repeated signals.
- Avoid modal dialogues for routine success/progress; do not steal focus or block batch processing.

### Acceptance tests
- Users can identify success/failure and locate details without opening hidden developer logs.
- Finishing a job shows verified output path with action to open it.
- A failure displays a clear message, preserves diagnostics and keeps other queued operations usable.

## P1 — UX-05: Clear queue history

**User story:** Remove old completed/failed/cancelled entries from Queue without deleting media files or interrupting active jobs.

### Requirements
- Add a clearly labeled **Clear History** button to the Queue view.
- Target only finished history by default: Completed / Failed / Cancelled; never remove or cancel active/pending tasks as a side effect.
- Explain exactly what is being deleted (history entries, not output/source files). Provide a confirmation when destructive or irreversible, with count.
- Consider `Clear completed` and `Clear all finished` if existing queue model supports filtering cleanly; a single `Clear History` button is acceptable for MVP.
- Keep behavior consistent with existing queue persistence (currently may be session-only). Do not promise deletion of logs/files outside managed history.
- Preserve error logs that are referenced by still-active jobs; clean only records owned by cleared entries.
- Disable the action when no eligible history exists. Update displayed counts/state immediately on success.

### Acceptance tests
- Clearing history with active jobs leaves them running and visible.
- Media files and verified outputs are unaffected.
- Empty Queue disables Clear History; repeat clicks are safe.

## Implementation order / dependency plan

1. **Audit and UX contracts:** inspect UI widgets/models, operation validation, queue persistence and signals; record actual behavior. Create an implementation checklist with screenshots or reproducible cases of current problems.
2. **UX-03 Validate & Preview**: improve underlying per-file result contract and present unambiguous ready/blocked feedback. This will be reused by Bulk Edit.
3. **UX-04 Operation feedback**: wire application events into prominent notifications/status and persistent queue records.
4. **UX-01 Bulk editor**: multi-select, mixed values and partial updates, per-file validation and collision-safe output planning.
5. **UX-02 Contextual help**: shared reusable control/metadata, coverage and accessibility.
6. **UX-05 Queue history clear**: queue model/service action plus UI and tests.
7. **UX regression pass:** verify existing Inspect, Remux, Convert, Compress, Queue, playback (if implemented), output extensions, dropdown geometry, external FFmpeg resolution, platform-specific UI and package startup.

This is a suggested order: Codex may change it after code audit if dependencies demand, but must record the reason.

## Architectural and quality gates

- UI must never construct raw FFmpeg commands or invoke FFmpeg directly; keep domain/application/infrastructure boundaries.
- Preserve nonblocking Qt behavior and typed validation; no `shell=True`.
- Preserve existing safe staging/no-overwrite behavior.
- Queue tasks remain immutable plan snapshots once queued.
- Ensure batch work does not silently affect unselected files.
- Add unit tests for view-model/application behavior plus focused PySide6 widget tests, and practical manual smoke tests on available OSes.
- Run project lint/tests and report exact commands/results, known gaps, and platform verification status.
- Before public release, separately finish packaging/licensing/security/release checklist. Passing UI tests does not imply production readiness.

## Codex starting instruction

Read `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, current UI/queue/validation code and this file. Audit how these five requirements fit the existing app. Produce `docs/PRE_RELEASE_UX_IMPLEMENTATION.md` with exact module/class changes, risks, acceptance tests and execution order. Implement **UX-03 only** as the first vertical slice unless repo constraints justify a smaller prerequisite. Run tests and leave the application runnable. Do not tackle all five features in one pass; do not mark untested work complete.
