# R1 — UI audit and migration map

Audit date: 2026-10-18. Scope: the current repository, before any R2 component
replacement. Read: AGENTS.md, ARCHITECTURE.md, ROADMAP.md, UI_UX_SPEC.md and
UI_OVERHAUL_CODEX.md. Source inspection, rather than the historical roadmap's
checkboxes, establishes the inventory below.

The new R1–R6 migration is the active development direction. Historical release,
Windows and GPU verification caveats in the old documents are not additional
features to implement in this UI audit, nor evidence that those platforms passed.
No application, domain, infrastructure or UI implementation changes are made in R1.

## 1. Current composition and proposed destinations

All source paths below are relative to `src/media_wrapper/`. Destination names
follow the UI spec; they describe future components, not existing classes.

| Existing component | Actual role | Migration decision and destination |
| --- | --- | --- |
| `main.py::main` | QApplication identity/icon, platform environment, logging/settings composition, shutdown cleanup; explicit smoke-test mode | Reuse composition and lifecycle; apply theme in R2 without changing binary/services setup |
| `ui/main_window.py::MainWindow` | Only production top-level window; composes six pages, routes dialogs/actions and renders shared state | Adapt incrementally to TopBar, mode navigation, nested splitters, panels and StatusBar in R3 |
| `MainWindow.navigation` / `pages` | QListWidget and QStackedWidget: Files/Inspect, Remux, Convert, Compress, Queue, Settings | Replace sidebar chrome with Workspace/Convert/Compress/Remux/Queue modes; Settings remains reachable from TopBar |
| `ui/views.py::FilesView` | Local drop target, extended-selection QListWidget, inspection buttons, summary, 11-column stream QTableWidget | Initially wrap in MediaLibraryPanel; adapt to MediaFileModel and view in R4; move stream/metadata details to Inspector |
| `ui/views.py::RemuxView` | Scroll area with copy-track list, container/destination, preservation policies, run/enqueue/cancel, progress, advanced argument preview | Reuse controls through a Remux Inspector adapter, then regroup in R4 |
| `ui/encoding_view.py::EncodingView` | Two independent scrollable instances, titled Convert and Compress, with typed request generation | Reuse request/apply/preset/capability behavior; adapt to separate contextual Inspector pages without losing either draft |
| `ui/views.py::QueueView` | Four-column task table, start/cancel/retry actions, definitions save/load, detailed text | Adapt in R5 to Processing Timeline plus accessible table/list and task details; keep Queue mode as full task-management entry |
| `ui/views.py::SettingsView` | Binary selection/detection, capability scan, GPU device/test options, logging and diagnostics export | Wrap as settings surface opened from TopBar in R3; preserve all controls in R4 |
| `MainWindow.output` | Global read-only QTextEdit for inspection, results, failures and action feedback | Replace presentation with notifications and expandable detail area; preserve full selectable text and error recovery guidance |
| `MainWindow.statusBar()` | Startup diagnostic location/settings warning; active binary status is currently in Settings | Adapt to persistent binary/encoder/task summary and notifications; retain diagnostic-path and settings warnings |
| QFileDialog calls | Multi-file input, binary folder, destinations, JSON profiles/queue definitions/diagnostics | Reuse native dialogs and filters; route through shared actions/controllers, preserve cancelled-dialog behavior |
| QMessageBox calls | Busy-close refusal and preference-save warning | Retain shutdown protection and visible save failures; restyle only where appropriate |
| `ui/views.py::PlaceholderView` | Defined generic label widget, not instantiated by the current shell | Do not mistake for a media preview. Remove only in R6 after reference/test review |
| `ui/installation_verification.py` | Explicit diagnostic entry point drives the real MainWindow/model through inspect and operations | Preserve as a regression client when shell APIs change; not a separate user workspace |

There is no existing media playback widget, thumbnail/waveform service, media
ruler, splitter layout, toolbar/menu action system, project document, or custom
item-model/delegate implementation. Existing QListWidget/QTableWidget objects
have Qt's internal models; they are not the proposed MediaFileModel/TaskModel.

## 2. Complete user-workflow map

Each row has a destination, an existing entry point and the behavior to preserve.
Rows marked **new** distinguish target-spec additions from existing functionality.

| ID | Existing entry point and workflow | New destination | Preserved contract / phase |
| --- | --- | --- | --- |
| W01 | Settings mode/folder/Browse/Detect; automatic startup detection | TopBar Settings → Binaries; StatusBar summary | External PATH or explicit custom/bundled directory, both active paths and versions, actionable failure, no hidden fallback; R3–R4 |
| W02 | Settings Select bundled sidecar folder | Same Binaries surface | Explicit selection of `ffmpeg/bin` beside frozen executable; missing pair fails, never substitutes PATH; R3–R4 |
| W03 | Files Add files / local URL drag-drop | TopBar Import and Media Library drop area | Multiple files, path validation/deduplication, spaces/Unicode, reject remote drops; R3–R4 |
| W04 | Inspect current / Inspect selected | Media Library actions/context actions | Current source differs from multi-selection; sequential probes, cached per-file success/failure, status summary; R4 |
| W05 | Cancel inspection / Clear files | Media Library toolbar | Cooperative probe cancellation, retained finished results, clear selection/cache; clearing library must not erase queued tasks; R4 |
| W06 | Current file row, summary, stream table, global inspection text | Shared selection → Preview metadata placeholder, Inspector metadata and Media Timeline | Real stream indices, codec/type, language, title/long codec tooltips, dimensions, rational FPS, bitrates, sample rate/channels/layout; unknown values remain unknown; R4–R5 |
| W07 | Checked Files streams and Remux track list | Remux Inspector stream selection | Two current views share `selected_streams` and per-file cached selections; incompatible tracks error, never silently drop; R4 |
| W08 | Remux container, destination/Browse, metadata and chapter controls | Remux Inspector output/policy groups | MKV/MP4, new filename, recent destination, preserve/strip policies and validation text; R4 |
| W09 | Remux Advanced details → Validate and preview | Inspector Advanced → Command preview | Background source re-probe, validated argv display; label distinctly from Source Preview; R4 |
| W10 | Run remux / Cancel remux, progress and completion output | Inspector Run/Cancel plus active-task summary in Processing panel | Direct OperationTask currently lives outside TaskQueue; preserve cancellation, real progress, verified result and retained-partial diagnostics; R3–R5 |
| W11 | Remux Add to queue | Inspector Add to Queue | Snapshot selected streams/output/policies; pending attempt, explicit Start; R4 |
| W12 | Convert/Compress per-track combos | Contextual Inspector → Streams | Copy/omit; video libx264/libx265/ffv1, audio aac/pcm_s16le, subtitle mov_text/srt/ass; codec/container and bitmap-to-text restrictions remain service-validated; R4 |
| W13 | Encoding track order, metadata/chapter selectors | Inspector stream order and preservation groups | Explicit indices in output order; every selected stream exactly once; preservation limitations retained; R4 |
| W14 | Width/height, FPS, audio bitrate | Inspector video/audio groups | Keep-original values, paired even dimensions, rational FPS, visible kb/s units and exact conversion to bit/s; R4 |
| W15 | Video default/quality/bitrate/target, CRF, speed preset; AAC bitrate/quality | Inspector basic/advanced rate control | CRF 0–51, AAC quality 1–5, bitrate choices, target MiB estimate/two-pass restrictions; inactive options and caveats stay clear; R4 |
| W16 | Editable starting presets / Apply | Inspector ProfilePicker + Apply preset | H.264/H.265/audio-only presets, explicit audio-only omission, editable results; not immutable one-click encoding; R4 |
| W17 | Import profile / Save-export profile | Inspector profile actions | Versioned validated JSON, current build/media validation, matching Convert/Compress form on import, no execution on import, no overwrite; R4 |
| W18 | CPU/GPU/Auto and tested GPU encoder | Inspector EncoderSelector; StatusBar execution summary | Runtime-tested evidence, CPU defaults, restrictions on GPU quality/two-pass modes, explicit CPU retry on failure; R4 |
| W19 | Restricted advanced arguments | Inspector Advanced field + Command preview | Only threads and muxing queue size with existing bounds; cannot override mapping/output/no-overwrite or introduce shell execution; R4 |
| W20 | Encoding destination/container and Validate and preview | Inspector output and advanced command display | MKV/MP4, exact argv arrays including two-pass previews; preview path differs from actual attempt path; R4 |
| W21 | Encoding Run / Add to queue | Inspector Run / Add to Queue | Immutable plan at enqueue, Run starts queue and opens Queue mode; later form edits do not mutate attempts; R4 |
| W22 | Batch folder/template/Add selected Files rows as batch | Inspector Batch group + Library multi-selection | `{stem}`, `{index}`, `{ext}`; selected rows, not just current source; all-or-nothing probing/validation and collision rejection, explicit start; R4 |
| W23 | Queue table, Start queue, row selection | Processing Timeline and equivalent table; Queue mode | Sequential attempts, Pending/Preparing/Running/Completed/Failed/Cancelled, filename/output/codec, unknown progress distinct, real speed/ETA; R5 |
| W24 | Cancel selected / Cancel all / Retry selected / Retry on CPU | Task row actions, keyboard/context actions and details | Operate by TaskRecord.id; fresh attempt and temp path, retain previous logs/partials; later jobs continue on failure/cancel; R5 |
| W25 | Queue details text | Task Inspector/details drawer | Executed argv, errors, estimated speed/ETA, partial/output paths, verified metadata and last 16000 diagnostic characters; keep selectable text; R5 |
| W26 | Save unfinished definitions / Load definitions | Processing/Queue toolbar | Local paths explicitly disclosed; revalidate changed/missing sources/build/output collisions, create new pending attempts, no auto-start/checkpointing; R5 |
| W27 | Settings Scan/refresh, optional runtime GPU tests, VAAPI device, Cancel scan | Settings → Capabilities | Listed vs tested vs failed/unknown, build/config/help/driver details, cancellable worker and cache invalidation on installation/device change; R4 |
| W28 | Settings log level, private-details checkbox, Export diagnostics | TopBar Diagnostics / Settings logging | Persist level; safe allowlisted export by default, explicit private-details opt-in; no raw log leakage into public summaries; R3–R4 |
| W29 | Global errors/results/status and busy-close message | StatusBar notifications, Inspector validation and expandable details | Preserve guidance and technical details, startup logging fallback, progress vs verified completion, no closing with live workers; R3–R6 |
| W30 | Normal-close preference save and startup restore | Existing settings service plus separate workspace layout store | Keep binary mode/folder, recent destination, container, advanced flag, log level, legacy page and window dimensions; preserve invalid/external-edited settings; R3 |
| N01 | **New:** media playback/seek | Source Preview | Metadata placeholder first; playback only if supported; explicit fallback never disables processing; R3/R6 |
| N02 | **New:** source time ruler and selectable lanes | Media Timeline | Actual FFprobe duration/stream metadata; no invented stream timing, waveforms, thumbnails or editing; R5 |
| N03 | **New:** splitter/workspace reset and timeline tab persistence | TopBar workspace controls, TimelinePanel | Default widths 23/47/30 and heights 68/32; QSettings restore/reset with validation; R3/R5 |
| N04 | **New:** open output, context menu and app shortcuts | Processing task actions / shared QActions | Only open an existing verified result via an OS adapter; action must not imply completion or open an unverified partial; R5–R6 |

The “project” label in the overhaul diagram has no corresponding backend project
model/save/load workflow. Treat it as workspace context, not a promise of an NLE
project format. Do not repurpose encoding profiles or saved queue definitions as
project files. Extra project features require separately defined scope.

## 3. State, models, controllers and signals

### Reuse these sources of truth

| Current owner | Actual data and semantics | Future adapter rule |
| --- | --- | --- |
| `ui/state.py::DesktopState` | Files/current_file, inspected source/media, inspections and stream-selection caches, remux form/output/command, busy/inspection/status flags | Retain one authoritative workspace selection; library/preview/inspector/media timeline observe it |
| `DesktopViewModel` | State, worker/thread lifetime, capability report/cancel event, direct remux task, TaskQueue | Reuse as initial workspace controller. `WorkspaceViewModel` is a future adapter/name, not reason to create a competing controller |
| `FilesView.file_list` | Extended selected rows currently live only in the widget | Introduce shared selected-path collection when adding models; keep current-path and multi-selection distinct |
| Each `EncodingView` | Most operation draft fields, per-stream encoder choices, destination, batch folder/template, `_media`, current preview | Wrap first. If extracted, keep separate typed Convert/Compress drafts and existing `ConversionRequest` conversion; do not lose values on every render/mode change |
| Settings widgets | Installation choices and GPU/log/export options | Preserve explicit detect/apply behavior; changing installation clears old media/capability evidence |
| `application/task_queue.py::TaskQueue` | `records`, running flag, active task and per-attempt binary selection | TaskModel observes records and emits incremental Qt model updates; it never launches its own second queue |
| `domain/tasks.py::TaskRecord` | Stable id, immutable plan, status/progress, argv, logs/error, partial/result | Use stable id for selection/actions, not sorted row index; retries are different records |
| `MainWindow` | `_preview_view`, selected task row, dialog routing and feedback rendering | Preserve correct result-to-form routing while replacing sender-identity and row-index assumptions |

`DesktopState` is not a complete store of current form state. “Single source of
truth” must not be implemented by discarding widget-owned choices before they are
mapped into explicit UI draft state. TaskQueue snapshots the current binaries at
add time; later global selection changes must not retarget those attempts.

### Signal and action inventory

- `MainWindow.navigation.currentRowChanged → pages.setCurrentIndex`; startup
  restores numeric page. New mode actions must preserve distinct source/task focus.
- File picker and `FilesView.files_dropped(object) → model.add_files`; current row
  calls `select_file`; item selection enables Inspect selected and supplies batch
  paths. Inspect current/selected call `inspect`/`inspect_many`; Cancel and Clear
  call `cancel_inspection`/`clear_files`.
- `FilesView.streams_selected(object)` and `RemuxView.streams_selected(object)`
  call `select_streams`. Current render uses QSignalBlocker to avoid feedback loops.
- Remux text/container/policy changes call `set_output`/`set_preservation`.
  Preview, Run, enqueue and Cancel route to `preview`, `remux`, `enqueue_remux`,
  `cancel_remux`. Advanced checkbox controls visibility only.
- Encoding field/track changes invalidate command preview; mode/audio controls
  update enabled fields; preset button applies an editable draft. Shell handlers
  use `encoding_sender()` to distinguish Convert/Compress and call `encode` with
  preview/run/enqueue, `enqueue_batch` or `exchange_profile`.
- `DesktopViewModel.changed() → MainWindow.render`; `encoding_preview_ready(object)`
  fills the originating form; `profile_loaded(object)` applies to the operation's
  matching form and changes mode. Do not disconnect these during reparenting.
- Detection/Inspection/RemuxPreparation/EncodingPreview/Capability/Service workers
  expose `finished(object)` and `failed(str)`; Inspection adds `progress(object)`.
  `_start` wires QThread start, success/failure, quit, deleteLater and cleanup.
- `TaskQueue.changed() → model._queue_changed → changed`; OperationTask emits
  `changed()` and `finished(bool, str)`. Queue start/cancel/retry actions call the
  existing controller/queue methods. Direct Remux has its own completion wiring.
- `ProcessRunner` supplies `finished(bool, str)`, stdout bytes, diagnostics text
  and progress objects beneath OperationTask. New views subscribe through the
  controller/task adapter, not directly to a competing process lifecycle.
- Settings installation edits invalidate detection/capabilities; Detect calls
  `detect`; sidecar action selects folder then detects. Scan/Cancel/device changes
  use `scan_capabilities`, `cancel_capabilities`, `invalidate_capabilities`.
- Log-level changes call `diagnostic_service.set_log_level`; diagnostics/queue
  save-load actions call `export_diagnostics`/`exchange_queue` through ServiceWorker.
- `closeEvent` refuses busy close; otherwise uses SettingsService.save and warns
  on failure. `main` deletes the window on quit and drains logging afterward.

### Keyboard and accessibility baseline

No explicit application QShortcut/QAction shortcuts, custom menus, tab-order
setup, accessible-name setters or label-buddy setup were found in the UI sources.
The current interface relies on native widgets' keyboard focus, editing,
selection, checkbox/button activation and read-only text selection/copy. These
native behaviors must survive new styling/delegates. Application shortcuts,
explicit semantic labels, predictable tab traversal, task context menus and an
accessible timeline table are R2–R6 additions requiring tests; they are not
already verified features. Avoid global Space/Delete shortcuts that interfere
with editing fields. Do not replace text status with color-only indicators.

## 4. Backend entry points to retain

| Workflow | Existing application/domain/infrastructure boundary |
| --- | --- |
| File selection/detection | `file_service.validate_files`; `binary_service.detect_binaries`; `binary_resolver.resolve` / `sidecar_directory` |
| Inspect | `InspectionBatch.run`, `MediaService.inspect`, cancellable probe service/parser → immutable MediaFile/MediaStream/MediaChapter |
| Remux preview/configuration | `MediaService.prepare_remux`, remux path validation, typed OperationPlan and StreamSelection |
| Convert/Compress | `conversion_service.conversion_plan`, `preview_conversion`, `hardware_selection.select_hardware`, `target_size.apply_target_size` |
| Policy and command construction | `operation_policy.validate_plan`, `operation_validation.validate_paths`, `operation_service.prepare_operation`, CommandBuilder |
| Execution/verification/publication | OperationTask, ProcessRunner, ProgressParser, no-overwrite `publish_output`; retain existing legacy RemuxTask adapter while its callers/tests remain |
| Sequential queue | `TaskQueue.add/start/cancel/cancel_all/retry/retry_cpu`, existing legal TaskStatus transitions |
| Profiles/batches | `profile_service.import_profile/export_profile`, domain profile schema, `batch_service.plan_batch` |
| Capabilities | `capability_service.scan_capabilities`, build inventory/cache, runtime GPU probe and CPU retry policy |
| Queue definitions | `queue_document_service.save_queue/load_queue`, strict versioned schema and source fingerprint revalidation |
| Diagnostics/settings | `diagnostic_service`, SettingsService, Preferences schema, SettingsRepository, AppPaths and rotating logging |

No services above need replacement to achieve the new visual layout. UI adapters
may expose their existing data/actions; FFmpeg arguments, codec policy, subprocess
execution, output staging and validation remain in their current layers.

## 5. Feature-parity risks and migration decisions

1. **Two meanings of preview.** Existing preview is argv text only. Keep it in
   Inspector Advanced and introduce Source Preview as a metadata placeholder.
   Playback failure is independent of external FFmpeg encoding capability.
2. **Direct Remux is not a queued record.** A timeline built solely from
   `queue.records` would hide Run Remux progress/cancellation. Initially expose
   `model.remux_task.record` as a separate active task presentation; route its
   cancel action to `cancel_remux`, not queue.cancel. Any later unification must
   preserve Run behavior and be separately regression-tested.
3. **Validated enqueue differs today.** Batch/profile import validates in workers;
   ordinary encoding enqueue builds a typed plan but full filesystem/build
   validation happens during preview/preparation. The target requires validated
   snapshots on Add to Queue. In R4 add a UI/application adapter invoking the
   existing preparation services asynchronously before adding a captured draft;
   retain execution-time revalidation. Do not claim the current enqueue already
   satisfies this stronger UI-spec contract.
4. **Import currently does not auto-inspect.** Add/drop populates the library;
   explicit Inspect actions trigger probing. Preserve those actions initially.
   If R4 adopts automatic metadata loading, reuse the cancellable inspection
   orchestration, define how subsequent imports are scheduled, and test it.
5. **Busy state is global.** Queue/direct Remux/worker activity disables most
   editing/selection/detection, while navigation and relevant cancel actions
   remain available. Do not accidentally relax concurrency rules by moving
   buttons. Independent configuration during processing is not existing behavior.
6. **Selection ownership and signal churn.** Preserve per-file Remux selections,
   operation-specific encoding choices, current source vs selected batch paths,
   and selected task id. Rebuilding tables on every `changed` currently scales
   poorly; model adapters must update rows without resetting user selection.
7. **Preferences are JSON, not QSettings.** Current version-1 schema rejects
   unknown keys and protects malformed/externally edited files. Implement the
   spec's QSettings workspace layout in a separate namespaced UI store (R3),
   leaving service preferences in the existing repository. Validate splitter
   bytes/sizes, mode and timeline keys; use defaults/reset on corruption.
   Do not reinterpret legacy page 5 (Settings) as a new mode index. Keep compatible
   legacy preferences and store stable new mode identifiers separately.
8. **GUI-thread I/O already exists.** Startup/close preferences, file selection
   validation and inline path checks currently perform synchronous filesystem
   work. The new no-file-I/O-on-GUI-thread rule is stronger than the baseline.
   Preserve behavior in wrappers, then schedule applicable I/O through existing
   workers in narrow tested slices; do not move it into paint/model data methods.
9. **Media timeline has limited timing data.** MediaFile has container duration
   and chapters; MediaStream lacks individual start/end intervals, decoded frames
   and waveform samples. Lanes represent stream presence over a source-level
   ruler, not verified per-stream coverage. Unknown duration needs a no-duration
   state; do not fabricate timing or a seekable range.
10. **Task progress is not a media ruler.** Use recorded percent/speed/ETA only;
    None means indeterminate. Preparing/verification may have no useful percent.
    Completion is TaskStatus.COMPLETED after verification/publication, not a fill
    reaching 100%. Preserve cancellation and failed/partial distinction.
11. **Profiles, units and hidden fields.** Preserve every EncodingView request
    field, supported range, preset application and profile round-trip. Basic mode
    must disclose active advanced choices, not reset or hide them silently.
12. **Diagnostics privacy and safety.** Retain private-export opt-in, exclusive
    file creation and source/output safety. Friendly notifications should retain
    expandable technical details; raw logs cannot become the safe export summary.
13. **Testing/packaging coupling.** Existing tests and installation verifier use
    MainWindow properties (`model`, `thread`, `source`, `binaries`) and specific
    widget handles/page indices. Keep temporary adapters and migrate assertions
    to semantic actions without deleting backend coverage. Package QSS/icons and
    any later optional Qt Multimedia plugins explicitly; do not assume FFmpeg
    command capability proves Qt playback support.
14. **Size/accessibility/native verification.** Current default is 900×650 with
    640×480 minimum, sidebar max width 170 and several fixed table heights. Target
    baseline is 1280×720, plus 1080p/DPI tests. Use splitters and scrollable forms;
    retain visible critical actions when collapsed/narrow. Linux offscreen tests
    are not native Windows, screen-reader or high-DPI sign-off.

## 6. Incremental migration and regression gates

R1 is the audit only. The following are proposed slices, not completed phases.

| Phase | Narrow implementation order | Required evidence |
| --- | --- | --- |
| R2 (UI-01/07 foundation) | Central tokens/QSS and one reusable PanelHeader/StatusChip/empty state demonstrated on an existing page; no shell replacement | Existing pages remain usable; focus/hover/disabled/error/loading states; contrast, keyboard focus and packaged resource loading |
| R3 (UI-01/06 placeholder) | Add toolbar/modes and splitters; wrap old views; introduce truthful Preview placeholder; separate QSettings layout store/reset | Existing workflows and shutdown intact; stable mode routing; restart/missing/corrupt layout; 23/47/30 and 68/32 defaults; resize/DPI/native matrix |
| R4 (UI-02/03) | Media model and shared selection, then contextual Inspector adapters, draft capture/validated enqueue and profile/batch controls | File/stream selection sync, every W01–W22/W27–W30 reachable, immutable queued options, all existing conversion and validation tests retained |
| R5 (UI-04/05) | Task model/delegate with accessible equivalent, direct-remux presentation, then source-time lanes and tab persistence | Cancel/retry/CPU retry/definitions/details parity, unknown progress, accurate stream metadata, independent source/task/tab state |
| R6 (UI-06/07) | Optional playback/fallback, shortcuts, scalability/accessibility/DPI polish, default rollout | Full suite and packaged smoke, Windows/Linux manual matrix, huge library/long names/missing binaries/codecs/failures, remove obsolete views only after parity |

Existing regression anchors to preserve:

- `tests/test_shell.py`: navigation, busy guards, file picker/drop, current vs
  selected files, real indices/stream synchronization, profiles/batch/diagnostics,
  capability invalidation/cancellation, preferences, queue failure/retry and
  real conversion. Add panel/mode/splitter semantics alongside these assertions.
- `tests/test_ui_remux.py`, `test_startup.py`, `test_distribution.py` and
  `ui/installation_verification.py`: real shell/task lifecycle, causal errors,
  entry-point cleanup, sidecar selection and packaged workflows.
- `tests/test_preferences.py`: defaults/Unicode, invalid schema, external edits,
  atomic save failure. Add separate QSettings layout tests rather than weakening
  the existing JSON protections.
- `tests/test_advanced_workflows.py`, `test_conversion.py`, `test_capabilities.py`:
  profile representability, build compatibility, batch collisions, restricted
  arguments, privacy, saved queues, subtitles/chapters and CPU/GPU policies.
- `tests/test_task_queue.py`, `test_tasks.py`, `test_operation_task.py`,
  `test_process_runner.py`, `test_progress.py`: immutable attempts, transitions,
  cancellation/retry, progress, publication verification and collision safety.
- Inspection/parser/presentation and operation/remux/core/integration tests remain
  unchanged service contracts. New UI tests must not replace these with mocks.

Recommended first R2 change: introduce the specified tokens and scoped QSS,
then demonstrate a reusable panel header and text-plus-icon status on one existing
page. Include focus/disabled/loading states and resource-loading coverage. Keep
all current pages, action routing and services intact; do not start the new shell
in the same slice.

## 7. R1 verification and completion

The inventory covers the six live pages, shell/global surfaces, dialogs,
controller/state owners, worker/task signals, native keyboard behavior, service
entry points, diagnostic launch path and unused placeholder. Every existing
user-facing action has a destination in W01–W30. New-only features are separately
identified in N01–N04. No component replacement or backend rewrite occurred.

End-of-audit verification: `.venv/bin/pytest -q` — **329 passed in 17.85s**,
including offscreen shell/startup and real-media regression tests. Source inventory
and action/signal mappings were checked against the implementation. No runtime
files changed during R1. Native Windows/DPI/accessibility validation is reserved
for the relevant later phase; this audit does not claim those checks passed.
R1 acceptance is satisfied: every current workflow has a destination. Next: R2.
