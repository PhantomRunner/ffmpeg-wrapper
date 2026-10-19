# Pre-release UX implementation plan

Public distribution is blocked until this milestone, existing release blockers and
an explicit publication command are satisfied. Portable candidates are not AppImage
or EXE installers: those packaging targets require separate verified work.
ROADMAP.md remains historical. No timeline will be reintroduced.

## Audit and execution order

1. **UX-03**: workers currently return command arrays; MainWindow routes encoding
   results through mutable _preview_view and automatically opens advanced settings.
   Remux has only a form-error label. Batch service stops at the first exception.
   Add application/validation_preview.py immutable candidate/result/report contracts,
   preserving typed errors and existing preview_conversion checks. Aggregate per-file
   errors and collisions without enqueueing. Add a shared UI presenter with pinned
   counts, accessible per-file detail and optional commands; bind immutable snapshots
   and reject late results after edits, source/capability changes or filesystem events.
   Keep existing execution-time validation; blocked reports disable Run/Queue.
   Batch result contract is implemented now; batch selection/partial queue UI belongs
   to UX-01. No automatic skipping or queueing from preview.
2. **UX-04**: main_window.render, TaskQueue.changed and OperationTask transitions
   currently feed output text and Queue. Add persistent action-area feedback keyed
   by task ID + transition, with details/Queue/open verified output actions.
   Test deduplication, failures, cancellation and no success before verification.
3. **UX-01**: FilesView already has multiple selection; batch_service.plan_batch
   applies one ConversionRequest and aborts on errors. Add application bulk draft/
   patch contracts, explicit changed fields, mixed values and per-file stream choices.
   Reuse UX-03 validation before explicit all-ready or selected-ready queue actions.
   Test five-file partial edits, mixed layouts, collisions and immutable queued plans.
4. **UX-02**: tooltips are ad hoc. Add shared accessible help disclosure and parameter
   metadata for Remux/EncodingView; explain definition, impact, usage and limitations.
   Test keyboard access, coverage, narrow windows and 200% scale.
5. **UX-05**: TaskQueue holds session-only records and binary references; QueueView
   has no history action. Add clear-finished service operation and counted confirmation,
   never removing Pending/Preparing/Running or deleting files. Test active job safety,
   empty state and repeated clearing.
6. Regression: native tests, real media processing, offscreen/DPI UI and packaging;
   Windows/physical display, licenses and other release gates remain explicitly open.

## UX-03 acceptance and risks

- Ready/Warnings/Blocked counts and file/output/container/streams/operation details.
- Errors retain validator cause and provide field-specific next steps.
- Commands remain read-only and optional; successful validation explicitly says Ready.
- Immutable request identity rejects out-of-order responses and invalidates on edits.
- Source/output-directory watchers invalidate observed external filesystem changes;
  execution always revalidates, including changes not delivered by platform watchers.
- Aggregate collision detection blocks every conflicting candidate, never just the last.
- Preview never creates output or modifies the queue; existing staged publication remains.
- Tests: success/mixed reports, all-valid batches, collisions, missing encoders,
  stale responses, changed settings, accessible text and narrow layouts.

## UX-03 implementation evidence — 2026-10-19

Implemented the single-operation vertical slice and reusable multi-file contract.
Application validation uses the existing fresh inspection, muxer/encoder checks,
plan/path validation and staged command builder. Immutable reports preserve
per-file errors, stream/encoder summaries, hardware warnings and command arrays;
colliding candidates are all blocked. Preview never queues partial batches.

Remux/Convert/Compress show pinned counts and an accessible nonmodal read-only
details window. Commands are an optional disclosure. Blocked results disable
current Run/Queue controls; existing execution validation remains authoritative.
Input edits, source/build/capability/queue context changes and source/output-folder
notifications invalidate results. Revision checks discard stale callbacks.
Native worker integration exposed a Qt callback-affinity issue; delivery now goes
through a QObject slot on the GUI thread, verified by the real-media regression.

Acceptance coverage includes all-ready and mixed reports, collision/reserved names,
missing encoder, warnings versus errors, routed/stale callbacks, edited container/
resolution, actual worker validation, filesystem changes and no-overwrite execution.
Existing shell tests now inspect the new command disclosure and staged preview
path while retaining their output safety assertions.

Batch editing and explicit partial-batch queue controls remain UX-01 work; the
current batch action retains all-or-nothing validation. UX-04/01/02/05 are pending.
Native Windows and physical screen-reader/display checks remain pending.

Verification commands/results:
- QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q — **401 passed in 27.16 s**.
- QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2 .venv/bin/pytest
  tests/test_validation_preview.py tests/test_workstation_polish.py
  tests/test_workspace.py -q — **19 passed**.
- .venv/bin/ruff check . and git diff --check — passed.
- Offscreen 1280×720 workspace and mixed-result dialog reviewed; corrected dialog
  palette contrast. This is not physical-display or Windows acceptance.
No release, tag, remote push or production publication performed.

## UX-04 — persistent operation feedback

Added a shared, nonmodal notification strip across workspaces. Queue and direct
Remux records drive added/preparing/running/verified-completed/failed/cancelled
notices. Progress updates replace the same notice; repeated signals do not duplicate
transitions. Validation and worker errors are also surfaced. Unacknowledged failures
remain prominent while later jobs proceed. Details retain diagnostics without
stealing focus; Go to Queue and Open output are explicit user actions. Open output
is available only for completed records containing verified result metadata.
No timeline is reintroduced. Tests cover deduplication, sticky failure, acknowledgment,
navigation and verification gating alongside existing real processing tests.
UX-04 verification: 30 targeted tests passed; Ruff and whitespace checks passed.

## UX-02 — contextual parameter help

Shared help metadata covers container, naming, stream mapping/codecs, rate control,
CRF, bitrates, target size, preset, resolution/FPS, hardware, audio, preservation
and batch naming. Each field has an adjacent keyboard-focusable ? action, detailed
tooltip and F1 shortcut; a scrollable, screen-bounded nonmodal help window provides
keyboard-readable explanations. Codec-specific CRF/AAC ranges describe only the
existing validated controls; no universal GPU CQ range or capability is invented.
Current build/runtime validation remains authoritative.

Visual review at 1280×720 corrected native button contrast and help remnants for
hidden rate-control rows. Normal layout/workflow tests: 17 passed. Keyboard/help/
workspace checks at 200%: 15 passed. Ruff and whitespace checks passed.
UX-01 remains deferred; this task does not implement Bulk Editor.

## UX-05 — clear finished queue history

TaskQueue.finished_history_ids/clear_history removes only Completed/Failed/Cancelled
session records not owned by the active task. Only those IDs lose their per-attempt
binary references; no source, output, partial file or on-disk log is deleted.
The Queue button shows the eligible count and is disabled when empty. Confirmation
defaults to No and captures IDs before opening, so jobs finishing while it is open
are not silently added to the deletion scope. Task-owned notification records are
removed along with cleared history; active diagnostics remain intact.

Tests verify cancellation of confirmation, captured scope, repeated clearing,
empty controls, file preservation, active reference protection and a real FFmpeg
job completing successfully while previous history is removed.

Final verification:
- Full suite: 406 passed in 30.27 s.
- Subsequently added real-active-job clearing regression and reran it with the
  help/feedback/history/layout suite at 200%: 10 passed.
- Ruff and git diff --check passed.
- Visual review: 1280×720 compact controls and persistent banner. Physical display,
  screen-reader and native Windows acceptance remain pending.

UX-02, UX-04 and UX-05 are implemented and locally verified. UX-01 Bulk Editor
remains pending. No public release, tag or push was performed; all release gates
and the explicit-publication-command requirement remain in force.

Owner direction: UX-01 is paused while preparing the Linux AppImage candidate.
This is not a waiver of public release gates and does not authorize publication.
