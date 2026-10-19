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
