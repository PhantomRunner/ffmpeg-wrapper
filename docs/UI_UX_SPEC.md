# FFmpeg UI Wrapper — UI/UX Specification v1.0

## Direction
Hybrid Adobe Premiere-inspired workstation, Balanced density, dark-first; PySide6 / Qt Widgets. Both Processing Timeline and Media Timeline are required but represent different data. This application is a media processing tool, not a nonlinear editor.

## Layout
```
MainWindow
├─ TopBar (add files, workspace selector, diagnostics, settings)
├─ Vertical QSplitter
│  ├─ Horizontal QSplitter
│  │  ├─ MediaLibraryPanel (23%)
│  │  ├─ PreviewPanel (47%)
│  │  └─ InspectorPanel (30%)
│  └─ TimelinePanel (30–35% height)
│     ├─ ProcessingTimelineView
│     └─ MediaTimelineView
└─ StatusBar
```
Save splitter layouts with QSettings and restore them. Provide reset layout action. Avoid fixed dimensions and support 1280x720 as baseline; test 1080p and DPI scaling.

## Design tokens
- bg: `#15171C`
- panel: `#22242B`
- control: `#30333C`
- accent: `#A99CF5`
- text: `#ECECF1`
- secondary text: `#A3A6B2`
- success: `#419883`, error: `#D46B76`, processing: `#8C79D7`
- standard body: 13–14px, controls 32–36px height, 8–12px spacing, 12–16px panel padding, 4–8px border radius.
- Include keyboard focus and hover states, WCAG-aware contrast, text/icon status indicators, reduced animation.

## Main interactions
1. User imports files via drag/drop or file picker; FFprobe metadata appears in library.
2. Selecting a file synchronizes Preview, Inspector and Media Timeline.
3. User selects Convert, Compress or Remux; contextual Inspector presents basic and advanced settings.
4. Add to Queue freezes a snapshot of validated operation options. Existing queued tasks do not mutate when the source controls change.
5. Start Queue executes tasks using independent process manager; UI stays responsive.
6. Logs available per task with friendly error and expandable technical details.

## Processing Timeline
Timeline-shaped queue, **not** a timecode ruler: each row is one task and horizontal fill represents 0–100% process completion. Show filename, codec/output, state, progress, speed, ETA if known; actions cancel/retry/open output. Accessible equivalent table/list view should be available. Support context menu, keyboard selection, resize.

## Media Timeline
Actual source time axis and stream lanes (V1/A1/A2/S1). Read-only initial version. Selecting lanes shows stream details, audio enable/export selection lives in Inspector. Start with approximate layout informed by FFprobe; no fake decoded waveforms or thumbnails. Optional later: waveform, generated thumbnails, range selection, preview seek.

## PySide6 component hierarchy
```
ui/
  main_window.py                 # QMainWindow and compositions
  theme/tokens.py, theme.qss     # palette, typography, style
  widgets/panel_header.py
  widgets/empty_state.py
  widgets/status_chip.py
  widgets/encoder_selector.py
  widgets/profile_picker.py
  panels/media_library_panel.py  # QListView or QTableView + MediaFileModel
  panels/preview_panel.py        # placeholder; QMediaPlayer/QVideoWidget if supported
  panels/inspector_panel.py      # contextual controls via stacked widget
  panels/processing_panel.py     # progress task model & delegate
  panels/media_timeline_panel.py # custom QGraphicsView later
  models/media_file_model.py
  models/task_model.py
  viewmodels/workspace_viewmodel.py
```
`QSplitter` for panels, `QStackedWidget` for inspector modes, `QAbstractTableModel` / `QAbstractListModel` for data, `QStyledItemDelegate` for task rows. `QGraphicsView`/`QGraphicsScene` for time-based media streams. Keep Qt widgets separate from FFmpeg command builders and process execution.

## MVP implementation milestones
- [ ] UI-01 Foundation: theme, main window, top bar, status bar, vertical/horizontal splitters, save/restore/reset workspace layout.
- [ ] UI-02 Library: drag/drop, file list, selection signals, empty/loading/error states; connect existing FFprobe service.
- [ ] UI-03 Inspector: stacked panels for metadata/remux/convert/compress; units and validation; advanced settings disclosure.
- [ ] UI-04 Processing timeline: task list model, live states, progress, cancel/retry; mock data during isolated UI tests then real signals.
- [ ] UI-05 Media timeline: read-only time ruler and lanes from real FFprobe streams; selection sync; no fake waveform.
- [ ] UI-06 Preview: metadata placeholder first; add actual playback using Qt Multimedia where codecs/backends work; fallback to thumbnail/placeholder and retain processing capability.
- [ ] UI-07 Polish: keyboard shortcuts, high-DPI, 1280x720, compact layout, accessibility, status notifications, UI tests on Windows/Linux.

## Acceptance criteria
- Main UI can be resized without clipped critical actions; panel sizes persist across runs.
- File selection is a single source of truth across all panels.
- Adding a task captures operation parameters at that moment.
- Two timeline modes can be switched without deleting queue state or source selection.
- UI never blocks while probing or processing; errors visible and nontechnical messages have detailed log toggle.
- No UI module directly constructs shell command strings or executes FFmpeg.
- Layout loads with a reasonable default if saved state is missing or corrupted.
