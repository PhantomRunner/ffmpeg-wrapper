"""One scoped inspector for all operations; controls emit typed field patches."""
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from html import escape

from PySide6.QtCore import QEvent, QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.domain.capabilities import GPU_ENCODERS
from media_wrapper.domain.containers import CONTAINERS
from media_wrapper.domain.draft import MIXED, EditScope
from media_wrapper.domain.encoding_presets import PRESETS
from media_wrapper.domain.inspection import InspectionStatus
from media_wrapper.domain.operation_policy import ENCODERS
from media_wrapper.domain.operations import MediaOperation, PreservationPolicy
from media_wrapper.domain.remux import Container
from media_wrapper.ui.parameter_help import HELP
from media_wrapper.ui.widgets.combo_box import ReadableComboBox
from media_wrapper.ui.widgets.controls import ActionButton


class InspectorLabel(QLabel):
    """Keep source names and destinations readable without widening the panel."""

    def __init__(self, text=''):
        super().__init__()
        self._full_text = ''
        self._single_line = None
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_content(text)

    def set_content(self, text, *, single_line=False):
        if text == self._full_text and single_line == self._single_line:
            return
        self._full_text = text
        self._single_line = single_line
        self.setWordWrap(not single_line)
        self.setAccessibleName(text)
        self.setToolTip(f'<qt>{escape(text)}</qt>' if '<' in text else text)
        self._refresh_text()

    def _refresh_text(self):
        text = self._full_text
        if self._single_line:
            text = self.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, self.contentsRect().width())
        if text != self.text():
            self.setText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_text()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._refresh_text()


class ParameterField(QWidget):
    reset_requested = Signal()

    def __init__(self, title, control, hint='', parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(3)
        self.label = QLabel(title)
        self.label.setWordWrap(True)
        self.label.setBuddy(control)
        self.label.setMinimumWidth(90)
        control.setAccessibleName(title)
        self.control = control
        actions = QWidget()
        self._actions = QHBoxLayout(actions)
        self._actions.setContentsMargins(0, 0, 0, 0)
        self._actions.addWidget(control, 1)
        reset = ActionButton('↺')
        reset.setAccessibleName(f'Reset {title}')
        reset.setToolTip(f'Reset {title} in the declared edit scope')
        reset.setFixedWidth(30)
        reset.clicked.connect(self.reset_requested)
        self.add_action(reset)
        form.addRow(self.label, actions)
        layout.addLayout(form)
        self.hint = QLabel(hint)
        self.hint.setWordWrap(True)
        self.hint.setProperty('role', 'fieldHelp')
        self.hint.setVisible(bool(hint))
        layout.addWidget(self.hint)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setProperty('validation', 'error')
        self.error.hide()
        layout.addWidget(self.error)

    def add_action(self, button):
        self._actions.addWidget(button)

    def show_error(self, text):
        self.error.setText(text)
        self.error.setVisible(bool(text))


class SettingsInspector(QWidget):
    field_changed = Signal(str, object)
    scope_changed = Signal(object)
    reset_field = Signal(str)
    reset_all = Signal()
    preset_requested = Signal(str)
    streams_changed = Signal(str, object)
    stream_profiles_changed = Signal(str, object)
    import_profile = Signal()
    export_profile = Signal()
    save_preset = Signal()
    manage_presets = Signal()
    operation_requested = Signal(object)
    command_requested = Signal()

    def __init__(self, parent=None, *, progressive=False):
        super().__init__(parent)
        self.progressive = progressive
        if progressive:
            self.setObjectName('processingInspector')
        self.setMinimumWidth(260)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        outer.addWidget(self.scroll, 1)
        self.rendering = False
        self.fields = {}
        self.groups = {}
        self.stream_key = None
        self.stream_item = None
        self._named_presets = {}
        self._preset_label = 'Custom'
        self._intent_target = None
        body = QWidget()
        body.setProperty('role', 'formBody')
        self.scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        self.heading = InspectorLabel()
        self.heading.set_content('Operation settings', single_line=True)
        self.heading.setProperty('role', 'panelTitle')
        layout.addWidget(self.heading)
        self.tabs = QTabBar()
        self.tabs.setAccessibleName('Processing settings level')
        self.tabs.setExpanding(False)
        for name in ('Quick', 'Custom', 'Advanced'):
            self.tabs.addTab(name)
        self.tabs.setVisible(progressive)
        layout.addWidget(self.tabs)
        self.scope = ReadableComboBox()
        self.scope.setAccessibleName('Edit scope')
        self.scope.currentIndexChanged.connect(self._scope_changed)
        layout.addWidget(self.scope)
        self.scope_note = QLabel()
        self.scope_note.setProperty('role', 'fieldHelp')
        self.scope_note.setWordWrap(True)
        layout.addWidget(self.scope_note)
        self.intent = ReadableComboBox()
        self.intent_field = ParameterField('Goal', self.intent)
        self.intent_field.reset_requested.connect(lambda: self.intent.setCurrentIndex(0))
        self.intent.currentIndexChanged.connect(self._render_preset_choices)
        self.intent_field.setVisible(progressive)
        layout.addWidget(self.intent_field)
        self.preset = ReadableComboBox()
        self.preset.setAccessibleName('Operation preset')
        self.preset.currentIndexChanged.connect(self._preset_changed)
        self.preset_field = ParameterField('Preset', self.preset)
        self.preset_field.reset_requested.connect(self.reset_all)
        layout.addWidget(self.preset_field)
        self.quick_summary = InspectorLabel()
        self.quick_summary.setProperty('role', 'fieldHelp')
        self.quick_summary.setVisible(progressive)
        layout.addWidget(self.quick_summary)
        self.config = QWidget()
        self.config_layout = QVBoxLayout(self.config)
        self.config_layout.setContentsMargins(0, 0, 0, 0)
        self.config_layout.setSpacing(12)
        layout.addWidget(self.config)

        self._section('media', 'Media')
        if progressive:
            self.operation = ReadableComboBox()
            self.operation.setAccessibleName('Processing operation')
            for operation in MediaOperation:
                self.operation.addItem(operation.value.title(), operation.value)
            self.operation.currentIndexChanged.connect(self._operation_changed)
            operation_field = ParameterField('Operation', self.operation)
            operation_field.reset_requested.connect(lambda: self.operation.setCurrentIndex(0))
            self.groups['media'][1].addWidget(operation_field)
        self._combo('container', 'Container', [(s.label, c) for c, s in CONTAINERS.items()], 'media')
        self._combo('video_encoder', 'Video codec', [('Copy', 'copy'), ('H.264', 'libx264'),
                    ('H.265 / HEVC', 'libx265'), ('AV1 (SVT)', 'libsvtav1'), ('AV1 (AOM)', 'libaom-av1'),
                    ('VP9', 'libvpx-vp9'), ('DNxHR', 'dnxhd'), ('ProRes', 'prores_ks'), ('FFV1', 'ffv1')], 'media')
        self._combo('mode', 'Rate control', [('Encoder default', 'default'), ('Quality (CRF)', 'quality'),
                    ('Bitrate', 'bitrate'), ('Target size (two pass)', 'target')], 'media')
        self._spin('crf', 'Quality (CRF)', 0, 51, 'media', hint='Lower = higher quality. CPU H.264/H.265 only.')
        self._spin('video_bitrate', 'Video bitrate', 32, 200000, 'media', 1000, ' kb/s')
        self._spin('target_size_bytes', 'Target size', 1, 1000000, 'media', 1048576, ' MiB',
                   'Approximate budget: one libx264 video and known-rate audio.')
        if progressive:
            self._add_size_limit()
        self._combo('preset', 'Encoder speed', [(n, n) for n in ('ultrafast', 'superfast', 'veryfast',
                    'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow')], 'media')
        self._combo('hardware_mode', 'Processing', [('Software only', 'CPU'), ('Require GPU', 'GPU'),
                    ('Automatic', 'Auto'), ('Prefer GPU, allow software', 'Prefer GPU')], 'media')
        self._combo('gpu_encoder', 'Tested encoder', [('Auto', 'auto')], 'media')
        self.hardware_note = QLabel('GPU requires a successful runtime test in Settings. Quality and target size use CPU.')
        self.hardware_note.setWordWrap(True)
        self.hardware_note.setProperty('role', 'fieldHelp')
        self.groups['media'][1].addWidget(self.hardware_note)

        self._section('audio', 'Audio')
        self.audio_toggle = QCheckBox('Audio settings')
        self.config_layout.insertWidget(self.config_layout.indexOf(self.groups['audio'][0]), self.audio_toggle)
        self.audio_toggle.toggled.connect(lambda checked: self.groups['audio'][0].setVisible(checked))
        self._combo('audio_encoder', 'Audio codec', [('Copy', 'copy'), ('AAC', 'aac'), ('PCM 16-bit', 'pcm_s16le'),
                    ('PCM 24-bit', 'pcm_s24le'), ('ALAC', 'alac'), ('FLAC', 'flac'), ('MP3', 'libmp3lame'),
                    ('Opus', 'libopus')], 'audio')
        self._combo('audio_mode', 'AAC control', [('Bitrate', 'bitrate'), ('Quality', 'quality')], 'audio')
        self._spin('audio_bitrate', 'Audio bitrate', 8, 512, 'audio', 1000, ' kb/s')
        self._spin('audio_quality', 'AAC quality', 1, 5, 'audio', hint='Higher = higher quality; variable output size.')

        self._section('streams', 'Streams')
        self.streams_toggle = QCheckBox('Streams and metadata')
        self.config_layout.insertWidget(self.config_layout.indexOf(self.groups['streams'][0]), self.streams_toggle)
        self.streams_toggle.toggled.connect(lambda checked: self.groups['streams'][0].setVisible(checked))
        self.stream_note = InspectorLabel('Select one inspected row to map its streams. Indices are per file.')
        self.stream_note.setProperty('role', 'fieldHelp')
        self.groups['streams'][1].addWidget(self.stream_note)
        self.tracks = QTableWidget(0, 3 if progressive else 2)
        self.tracks.setHorizontalHeaderLabels(['Source stream', 'Action', 'Settings'] if progressive else ['Source stream', 'Action'])
        self.tracks.horizontalHeader().setStretchLastSection(True)
        self.tracks.verticalHeader().hide()
        self.tracks.setMinimumHeight(85)
        self.tracks.setMaximumHeight(180)
        self.tracks.setAccessibleName('Per-file stream mapping')
        self.groups['streams'][1].addWidget(self.tracks)
        for name, title in (('metadata_policy', 'Metadata'), ('chapter_policy', 'Chapters')):
            self._combo(name, title, [('Preserve', PreservationPolicy.PRESERVE),
                        ('Strip', PreservationPolicy.STRIP)], 'streams')

        self._section('output', 'Output')
        self._line('folder', 'Folder', 'output', 'Empty = source folder')
        browse = ActionButton('…')
        browse.setAccessibleName('Choose output folder')
        browse.setToolTip('Choose output folder')
        browse.setFixedWidth(30)
        browse.clicked.connect(self._browse)
        self.fields['folder'].add_action(browse)
        self._line('template', 'Name template', 'output', '{name}_{operation}')
        self.fields['template'].hint.setText('Tokens: {name}, {operation}, {index}, {ext}, {stem}. Extension follows the container.')
        self.fields['template'].hint.setVisible(not progressive)
        if progressive:
            self.fields['template'].control.setToolTip(self.fields['template'].hint.text())
        self.auto_number = QCheckBox('Auto-number output conflicts')
        self.auto_number.setToolTip('Choose a new unique filename. Existing files are never replaced.')
        self.auto_number.toggled.connect(lambda value: self._emit('auto_number', value))
        self.groups['output'][1].addWidget(self.auto_number)
        self.output_preview = InspectorLabel('Destination is resolved and checked per file during validation.')
        self.output_preview.setProperty('role', 'fieldHelp')
        self.groups['output'][1].addWidget(self.output_preview)
        self.size_note = QLabel('Size unknown until encoded.')
        self.size_note.setWordWrap(True)
        self.size_note.setProperty('role', 'fieldHelp')
        self.groups['output'][1].addWidget(self.size_note)

        self._section('advanced', 'Advanced')
        self.advanced_toggle = QCheckBox('Advanced settings')
        self.config_layout.insertWidget(self.config_layout.indexOf(self.groups['advanced'][0]), self.advanced_toggle)
        self.advanced_toggle.toggled.connect(lambda checked: self.groups['advanced'][0].setVisible(checked))
        self._spin('width', 'Width', 0, 16384, 'advanced', suffix=' px', hint='0 = keep original; provide both even dimensions to resize.')
        self._spin('height', 'Height', 0, 16384, 'advanced', suffix=' px')
        self._line('fps', 'Frame rate', 'advanced', 'Keep original, or 30000/1001')
        self._line('track_order', 'Stream order', 'advanced', 'Per-file indices, e.g. 2,0,3')
        self._line('custom_arguments', 'Extra options', 'advanced', '-threads 2 -max_muxing_queue_size 1024')
        if progressive:
            self._line('codec_profile', 'Video profile', 'advanced', 'Encoder default')
            self._line('pixel_format', 'Pixel format', 'advanced', 'Preserve when possible')
            self.verify_decode = QCheckBox('Verify by decoding')
            self.verify_decode.setToolTip('Decode the entire output to check media integrity.')
            self.verify_decode.toggled.connect(lambda enabled: self._emit('deep_verify', enabled))
            self.groups['advanced'][1].addWidget(self.verify_decode)
            command = ActionButton('View FFmpeg command')
            command.clicked.connect(self.command_requested)
            self.groups['advanced'][1].addWidget(command)
        self.profile_import = ActionButton('Import profile…')
        self.profile_export = ActionButton('Export profile…')
        self.profile_import.clicked.connect(self.import_profile)
        self.profile_export.clicked.connect(self.export_profile)
        self.groups['advanced'][1].addWidget(self.profile_import)
        self.groups['advanced'][1].addWidget(self.profile_export)
        for name in ('preset', 'hardware_mode', 'gpu_encoder'):
            self.groups['media'][1].removeWidget(self.fields[name])
            self.groups['advanced'][1].addWidget(self.fields[name])
        self.groups['media'][1].removeWidget(self.hardware_note)
        self.groups['advanced'][1].addWidget(self.hardware_note)
        self._preset_actions = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        for title, signal in (('Save preset…', self.save_preset), ('Manage presets…', self.manage_presets),
                              ('Reset overrides', self.reset_all)):
            button = ActionButton(title)
            button.clicked.connect(signal)
            if progressive:
                self._preset_actions.addWidget(button)
            else:
                self.config_layout.addWidget(button)
        if progressive:
            layout.addLayout(self._preset_actions)
            self.scroll.viewport().installEventFilter(self)
            for toggle in (self.audio_toggle, self.streams_toggle, self.advanced_toggle):
                toggle.hide()
        layout.addStretch()
        self.config_layout.removeWidget(self.groups['output'][0])
        outer.addWidget(self.groups['output'][0])
        self._body_layout = layout
        self._outer_layout = outer
        self._geometry_location = 'advanced'
        self._sections = {}
        self.tabs.currentChanged.connect(self._tab_visibility)
        self._tab_visibility()

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            margins = self._body_layout.contentsMargins()
            available = event.size().width() - margins.left() - margins.right()
            actions = self._preset_actions
            needed = sum(actions.itemAt(i).widget().minimumSizeHint().width() for i in range(actions.count()))
            needed += actions.spacing() * (actions.count() - 1)
            actions.setDirection(QBoxLayout.Direction.LeftToRight if available >= needed
                                 else QBoxLayout.Direction.TopToBottom)
        return super().eventFilter(watched, event)

    def ensureWidgetVisible(self, widget):
        if self.groups['output'][0].isAncestorOf(widget):
            return
        if self.progressive:
            for name, index in (('media', 1), ('audio', 1), ('streams', 2), ('advanced', 2)):
                if self.groups[name][0].isAncestorOf(widget):
                    self.tabs.setCurrentIndex(index)
                    self.scroll.ensureWidgetVisible(widget)
                    return
        for name, toggle in (('audio', self.audio_toggle), ('streams', self.streams_toggle), ('advanced', self.advanced_toggle)):
            if self.groups[name][0].isAncestorOf(widget):
                toggle.setChecked(True)
                self.groups[name][0].show()
        self.scroll.ensureWidgetVisible(widget)

    def _section(self, name, title):
        box = QGroupBox(title)
        inner = QVBoxLayout(box)
        inner.setSpacing(10)
        self.config_layout.addWidget(box)
        self.groups[name] = box, inner

    def _field(self, name, title, control, section, hint=''):
        field = ParameterField(title, control, hint)
        help_key = {'width': 'video_width', 'height': 'video_height', 'target_size_bytes': 'target_size'}.get(name, name)
        if help_key in HELP:
            control.setToolTip(HELP[help_key][1])
        field.reset_requested.connect(lambda: self.reset_field.emit(name))
        self.fields[name] = field
        self.groups[section][1].addWidget(field)
        return control

    def _combo(self, name, title, choices, section):
        control = self._field(name, title, ReadableComboBox(), section)
        for label, value in choices:
            control.addItem(label, value)
        control.currentIndexChanged.connect(lambda: self._emit(name, control.currentData()))

    def _spin(self, name, title, low, high, section, multiplier=1, suffix='', hint=''):
        control = self._field(name, title, QSpinBox(), section, hint)
        control.setRange(low - 1, high)
        control.setSpecialValueText('Mixed')
        control.setSuffix(suffix)
        if name in ('width', 'height'):
            control.setSingleStep(2)
        control.valueChanged.connect(lambda value: self._emit(name, (None if value == 0 and name in ('width', 'height') else value * multiplier))
                                     if value >= low else None)

    def _line(self, name, title, section, placeholder):
        control = self._field(name, title, QLineEdit(), section)
        control.setPlaceholderText(placeholder)
        control.setProperty('defaultPlaceholder', placeholder)
        control.editingFinished.connect(lambda: self._emit(name, control.text()))

    def _tab_visibility(self, *_):
        if not self.progressive:
            return
        tab = self.tabs.currentIndex()
        self.config.setVisible(tab != 0)
        for name, expected in (('media', 1), ('audio', 1), ('streams', 2), ('advanced', 2)):
            self.groups[name][0].setVisible(tab == expected and self._sections.get(name, True))
        for widget in (self.intent_field, self.preset_field, self.quick_summary):
            widget.setVisible(tab == 0)
        box = self.groups['output'][0]
        if tab == 0 and self._body_layout.indexOf(box) < 0:
            self._outer_layout.removeWidget(box)
            self._body_layout.insertWidget(self._body_layout.count() - 1, box)
            box.show()
        elif tab != 0 and self._outer_layout.indexOf(box) < 0:
            self._body_layout.removeWidget(box)
            self._outer_layout.addWidget(box)
            box.show()
        self.auto_number.setVisible(tab != 0)

    def _operation_changed(self, *_):
        if not self.rendering and self.operation.currentData() not in (None, MIXED):
            self.operation_requested.emit(MediaOperation(self.operation.currentData()))

    def _render_preset_choices(self, *_):
        if not self.progressive:
            return
        category = self.intent.currentData()
        with QSignalBlocker(self.preset):
            self.preset.clear()
            self.preset.addItem(self._preset_label, '')
            ordered = sorted(self._named_presets.items(), key=lambda item: (not item[1].favorite, item[0].casefold()))
            for name, entry in ordered:
                if category and entry.category != category:
                    continue
                self.preset.addItem(('★ ' if entry.favorite else '') + name, 'named:' + name)
                self.preset.setItemData(self.preset.count() - 1, entry.description, Qt.ItemDataRole.ToolTipRole)

    def _add_size_limit(self):
        self.limit_value = QLineEdit()
        self.limit_value.setPlaceholderText('e.g. 250')
        self.limit_value.setAccessibleName('Maximum output size value')
        self.limit_value.setMinimumWidth(55)
        self.limit_value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.limit_unit = ReadableComboBox()
        self.limit_unit.setAccessibleName('Maximum output size unit')
        self.limit_unit.setMinimumContentsLength(3)
        for unit in ('MiB', 'MB', 'MiB/min', 'MB/min', '%'):
            self.limit_unit.addItem(unit, unit)
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.limit_value, 2)
        row.addWidget(self.limit_unit, 1)
        self.size_limit = ParameterField('Maximum size', box, 'A percentage is the reduction from the source size.')
        self.size_limit.reset_requested.connect(lambda: self.reset_field.emit('target_size'))
        self.groups['media'][1].addWidget(self.size_limit)
        self.limit_value.editingFinished.connect(self._size_limit_changed)
        self.limit_unit.currentIndexChanged.connect(self._size_limit_changed)

    def _size_limit_changed(self, *_):
        raw = self.limit_value.text().strip()
        if self.rendering or not raw:
            return
        unit = self.limit_unit.currentData()
        try:
            value = Decimal(raw)
            if not value.is_finite() or value <= 0 or (unit == '%' and value >= 100):
                raise InvalidOperation
        except InvalidOperation:
            self.size_limit.show_error('Enter a positive number under 100 for a percentage, or choose a size unit.'
                                       if unit == '%' else 'Enter a positive number for the size limit.')
            return
        self.size_limit.show_error('')
        self._emit('target_size', (raw, unit))

    def _render_size_limit(self, draft, show):
        limit = draft.value('target_size')
        legacy = draft.value('target_size_bytes')
        with QSignalBlocker(self.limit_value), QSignalBlocker(self.limit_unit):
            if not limit and legacy not in (None, MIXED):
                limit = (str(Decimal(legacy) / Decimal(1048576)), 'MiB')
            self.limit_value.setText(limit[0] if isinstance(limit, tuple) else '')
            self.limit_value.setPlaceholderText('Mixed — enter a new limit' if limit is MIXED else 'e.g. 250')
            self.limit_unit.setCurrentIndex(self.limit_unit.findData(limit[1]) if isinstance(limit, tuple) else 0)
        self.size_limit.setVisible(show)

    def _emit(self, name, value):
        if self.rendering or value is MIXED:
            return
        if name == 'audio_mode':
            name, value = 'audio_quality', 2 if value == 'quality' else None
        if name in ('metadata_policy', 'chapter_policy'):
            value = PreservationPolicy(value)
        if name == 'container':
            value = Container(value)
        if name in ('codec_profile', 'pixel_format'):
            value = value.strip() or None
        if name == 'track_order':
            try:
                value = tuple(int(i.strip()) for i in value.split(',')) if value.strip() else ()
            except ValueError:
                self.fields[name].show_error('Use comma-separated stream indices.')
                return
        self.fields[name].show_error('') if name in self.fields else None
        self.field_changed.emit(name, value)

    def _scope_changed(self):
        if not self.rendering:
            self.scope_changed.emit(EditScope(self.scope.currentData()))

    def _preset_changed(self):
        if not self.rendering and self.preset.currentData():
            self.preset_requested.emit(self.preset.currentData())

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose output folder')
        if folder:
            self._emit('folder', folder)

    def render(self, draft, capabilities=None, named_presets=()):
        self.rendering = True
        try:
            active = draft.outputs.get(draft.active_output_id) if draft.multiple_outputs else None
            item = draft.items.get(active.source_id) if active else (
                draft.items.get(draft.selected[0]) if len(draft.selected) == 1 else None)
            targets = draft.editable_outputs() if draft.multiple_outputs else draft.editable()
            self.heading.set_content(f'{item.path.name} / {active.label}' if active else draft.operation.value.title() + ' settings',
                                     single_line=True)
            self.scope.clear()
            if draft.multiple_outputs:
                self.scope.addItem('Edit: Focused output', EditScope.ACTIVE.value)
                selected = len(draft.selected_outputs)
                included = sum(output.included for output in draft.outputs.values())
                noun = 'outputs'
            else:
                selected = len(draft.selected)
                included = sum(item.included for item in draft.items.values())
                noun = 'files'
            self.scope.addItem(f'Edit: Selected {noun} ({selected})', EditScope.SELECTED.value)
            self.scope.addItem(f'Edit: Included {noun} ({included})', EditScope.INCLUDED.value)
            self.scope.setCurrentIndex(self.scope.findData(draft.scope.value))
            waiting = any(not source.inspection or source.inspection.status in (InspectionStatus.PENDING, InspectionStatus.RUNNING)
                          for source in draft.targets())
            count = len(targets)
            count_text = noun.rstrip('s') if count == 1 else noun
            self.scope_note.setText('Wait for probing in this scope, or choose a different scope.' if waiting else
                                    f'{count} {count_text} editable · Changes apply to this scope')
            self.config.setEnabled(bool(targets) and not waiting)
            self.groups['output'][0].setEnabled(bool(targets) and not waiting)
            self.preset.setEnabled(bool(targets) and not waiting)
            configurations = tuple((draft.items[output.source_id], output, output.operation) for output in targets) if draft.multiple_outputs else (
                tuple((source, source, draft.operation) for source in targets))
            names = [config.options[op].preset_name + (' (modified)' if config.options[op].preset_modified else '')
                     for _, config, op in configurations]
            self._preset_label = 'Mixed' if names and len(set(names)) > 1 else names[0] if names and names[0] else 'Custom'
            operations = {op for _, _, op in configurations}
            if self.progressive:
                self._named_presets = named_presets
                old_category = self.intent.currentData()
                option = active.options.get(active.operation) if active else None
                preset_name = option.preset_name if option else ''
                intent_target = (active.id if active else None, preset_name)
                if intent_target != self._intent_target:
                    self._intent_target = intent_target
                    if entry := named_presets.get(preset_name):
                        old_category = entry.category
                with QSignalBlocker(self.intent):
                    self.intent.clear()
                    self.intent.addItem('All goals', '')
                    for category in dict.fromkeys(entry.category for entry in named_presets.values()):
                        self.intent.addItem(category, category)
                    self.intent.setCurrentIndex(max(0, self.intent.findData(old_category)))
                self._render_preset_choices()
                with QSignalBlocker(self.operation):
                    old_mixed = self.operation.findData(MIXED)
                    if old_mixed >= 0:
                        self.operation.removeItem(old_mixed)
                    if len(operations) > 1:
                        self.operation.addItem('Mixed', MIXED)
                    value = MIXED if len(operations) > 1 else draft.operation.value
                    self.operation.setCurrentIndex(self.operation.findData(value))
                self._render_quick_summary(item, active)
            else:
                self.preset.clear()
                self.preset.addItem(self._preset_label, '')
                if draft.operation != MediaOperation.REMUX:
                    for index, preset in enumerate(PRESETS):
                        self.preset.addItem(preset.name, f'builtin:{index}')
                for name in named_presets:
                    self.preset.addItem(name, 'named:' + name)
            gpu = self.fields['gpu_encoder'].control
            gpu.clear()
            gpu.addItem('Auto', 'auto')
            for name in sorted(capabilities.working() if capabilities else ()):
                gpu.addItem(name, name)
            has_video, has_audio = (
                any(stream.kind == kind and not getattr(stream, 'is_artwork', False) and
                    dict(config.options[op].request.tracks).get(stream.index, 'omit') != 'omit'
                    for source, config, op in configurations for stream in source.media.streams)
                for kind in ('video', 'audio')
            )
            remux = (operations == {MediaOperation.REMUX} if operations else draft.operation == MediaOperation.REMUX)
            encode_scope = not remux and len(operations) <= 1
            if self.progressive:
                self._sections = {'media': True, 'audio': encode_scope and has_audio,
                                  'streams': True, 'advanced': True}
                self.fields['track_order'].setVisible(len(targets) == 1)
            else:
                self.audio_toggle.setVisible(not remux and has_audio and has_video)
                self.groups['audio'][0].setVisible(not remux and has_audio and (not has_video or self.audio_toggle.isChecked()))
                self.streams_toggle.setVisible(draft.operation == MediaOperation.COMPRESS)
                self.groups['streams'][0].setVisible(draft.operation != MediaOperation.COMPRESS or self.streams_toggle.isChecked())
                self.advanced_toggle.setVisible(not remux)
                self.groups['advanced'][0].setVisible(not remux and self.advanced_toggle.isChecked())
            location = 'media' if self.progressive or draft.operation == MediaOperation.CONVERT else 'advanced'
            if location != self._geometry_location:
                for name in ('width', 'height', 'fps'):
                    self.groups[self._geometry_location][1].removeWidget(self.fields[name])
                    self.groups[location][1].addWidget(self.fields[name])
                self._geometry_location = location
            mode, audio_quality = draft.value('mode'), draft.value('audio_quality')
            for name, field in self.fields.items():
                value = ('bitrate' if audio_quality is None else MIXED if audio_quality is MIXED else 'quality') if name == 'audio_mode' else draft.value(name)
                control = field.control
                with QSignalBlocker(control):
                    if isinstance(control, ReadableComboBox):
                        while control.findData(MIXED) >= 0:
                            control.removeItem(control.findData(MIXED))
                        index = control.findData(value)
                        if value is MIXED:
                            control.addItem('Mixed', MIXED)
                            index = control.count() - 1
                        elif index < 0 and value is not None:
                            control.addItem(f'{value} (unavailable)', value)
                            index = control.count() - 1
                        control.setCurrentIndex(max(0, index))
                    elif isinstance(control, QSpinBox):
                        multiplier = 1000 if name in ('audio_bitrate', 'video_bitrate') else 1048576 if name == 'target_size_bytes' else 1
                        default = 100 if name == 'target_size_bytes' else 2 if name == 'audio_quality' else 0
                        control.setValue(control.minimum() if value is MIXED else int(value / multiplier) if value is not None else default)
                    else:
                        control.setText('' if value is None or value is MIXED else ','.join(map(str, value)) if isinstance(value, tuple) else str(value))
                        control.setPlaceholderText('Mixed — enter a value to apply' if value is MIXED
                                                   else control.property('defaultPlaceholder') or '')
                visible = True
                if name in ('video_encoder', 'mode', 'crf', 'video_bitrate', 'target_size_bytes', 'preset', 'hardware_mode', 'gpu_encoder'):
                    visible = encode_scope and has_video
                if name == 'crf':
                    visible = visible and mode == 'quality'
                elif name == 'video_bitrate':
                    visible = visible and mode == 'bitrate'
                elif name == 'target_size_bytes':
                    visible = visible and mode == 'target' and not self.progressive
                elif name == 'audio_quality':
                    visible = has_audio and audio_quality is not None
                elif name == 'audio_bitrate':
                    visible = has_audio and (audio_quality is None or audio_quality is MIXED)
                elif name in ('width', 'height', 'fps', 'codec_profile', 'pixel_format'):
                    visible = encode_scope and has_video
                elif name in ('track_order', 'custom_arguments') and self.progressive:
                    visible = len(targets) == 1
                field.setVisible(visible)
            self.hardware_note.setVisible(not remux and has_video)
            if capabilities:
                for name in ('video_encoder', 'audio_encoder'):
                    control = self.fields[name].control
                    for index in range(control.count()):
                        value = control.itemData(index)
                        available = value not in ENCODERS or value in capabilities.build.encoders
                        control.model().item(index).setEnabled(available)
                hardware = self.fields['hardware_mode'].control
                hardware.model().item(hardware.findData('GPU')).setEnabled(bool(capabilities.working()))
            encoder, hardware = draft.value('video_encoder'), draft.value('hardware_mode')
            quality_supported = encoder in ('libx264', 'libx265', 'libsvtav1', 'libaom-av1', 'libvpx-vp9', MIXED) and hardware != 'GPU'
            self.fields['crf'].control.setEnabled(quality_supported)
            self.fields['crf'].show_error('Choose a software encoder with quality control, or use Encoder default.'
                                          if has_video and not remux and mode == 'quality' and not quality_supported else '')
            audio_encoder = draft.value('audio_encoder')
            aac = audio_encoder in ('aac', MIXED)
            bitrate = audio_encoder in ('aac', 'libmp3lame', 'libopus', MIXED)
            self.fields['audio_mode'].setVisible(encode_scope and has_audio and aac)
            self.fields['audio_quality'].setVisible(encode_scope and has_audio and aac and audio_quality is not None)
            self.fields['audio_bitrate'].setVisible(encode_scope and has_audio and bitrate and
                                                  (not aac or audio_quality is None or audio_quality is MIXED))
            if self.progressive:
                self._render_size_limit(draft, encode_scope and has_video and mode == 'target')
                deep_verify = draft.value('deep_verify')
                self.verify_decode.setTristate(deep_verify is MIXED)
                self.verify_decode.setCheckState(Qt.CheckState.PartiallyChecked if deep_verify is MIXED else
                                                 Qt.CheckState.Checked if deep_verify else Qt.CheckState.Unchecked)
                self._tab_visibility()
            auto = draft.value('auto_number')
            self.auto_number.setTristate(auto is MIXED)
            self.auto_number.setCheckState(Qt.CheckState.PartiallyChecked if auto is MIXED else Qt.CheckState.Checked if auto else Qt.CheckState.Unchecked)
            source = item if item and item.inspected else None
            self._render_streams(source, active.operation if active else draft.operation, capabilities, active)
        finally:
            self.rendering = False

    def _render_quick_summary(self, source, active):
        options = active.options.get(active.operation) if active else None
        if not options or not source or not source.inspected:
            self.quick_summary.set_content('Choose an inspected output, then select a goal and preset.')
            return
        actions = dict(options.request.tracks)
        codecs = []
        video = sum(stream.kind == 'video' and not getattr(stream, 'is_artwork', False) and actions.get(stream.index) != 'omit'
                    for stream in source.media.streams if stream.index in actions)
        audio = sum(stream.kind == 'audio' and actions.get(stream.index) != 'omit'
                    for stream in source.media.streams if stream.index in actions)
        audio_labels = [stream.title for stream in source.media.streams
                        if stream.kind == 'audio' and actions.get(stream.index, 'omit') != 'omit' and stream.title]
        tracks = f'{video} video · {audio} audio'
        if audio_labels:
            tracks += ' (' + ', '.join(audio_labels) + ')'
        for stream in source.media.streams:
            action = actions.get(stream.index, 'omit')
            if action == 'omit' or stream.kind not in ('video', 'audio'):
                continue
            control = self.fields[f'{stream.kind}_encoder'].control
            choice = control.findData(action)
            label = f'Copy {stream.codec}' if action == 'copy' else control.itemText(choice) if choice >= 0 else action
            if action == 'dnxhd' and options.request.codec_profile:
                label = options.request.codec_profile.upper().replace('_', ' ')
            codecs.append(label)
        parts = [CONTAINERS[options.request.container].label, *dict.fromkeys(codecs), tracks]
        self.quick_summary.set_content(' · '.join(parts))

    def _render_streams(self, item, operation, capabilities, output=None):
        request = (output or item).options[operation].request if item else None
        key = ((output or item).id if item else None, request.tracks if request else (),
               request.stream_profiles if request and self.progressive else (), operation,
               capabilities.build.identity if capabilities else None)
        self.tracks.setVisible(item is not None)
        self.stream_note.set_content(f'Stream mapping for this output of {item.path.name}.' if item else
                                'Select one inspected row to map its streams. Indices are per file.')
        if key == self.stream_key:
            return
        self.stream_key, self.stream_item = key, item
        self.stream_output, self.stream_request = output, request
        self.tracks.setRowCount(len(item.media.streams) if item else 0)
        for row, stream in enumerate(item.media.streams if item else ()):
            cell = QTableWidgetItem(f'{stream.index}: {stream.title or stream.kind} / {stream.codec} / {stream.language or "und"}')
            cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.tracks.setItem(row, 0, cell)
            combo = ReadableComboBox()
            combo.addItem('Exclude' if self.progressive else 'Omit', 'omit')
            if stream.index is not None:
                combo.addItem('Copy', 'copy')
                if operation != MediaOperation.REMUX:
                    for encoder, (kind, _) in ENCODERS.items():
                        if kind == stream.kind and encoder not in GPU_ENCODERS and (not capabilities or encoder in capabilities.build.encoders):
                            combo.addItem(f'Convert to {encoder}' if self.progressive else encoder, encoder)
            value = dict(request.tracks).get(stream.index, 'omit')
            if combo.findData(value) < 0:
                combo.addItem(value + ' (unavailable)', value)
            combo.setCurrentIndex(combo.findData(value))
            self.tracks.setCellWidget(row, 1, combo)
            combo.currentIndexChanged.connect(self._streams_edited)
            if self.progressive:
                button = ActionButton('Options…')
                button.setAccessibleName(f'Settings for stream {stream.index}')
                button.setEnabled(value not in ('omit', 'copy') and stream.kind in ('video', 'audio'))
                button.clicked.connect(lambda _checked=False, stream=stream: self._edit_stream(stream))
                self.tracks.setCellWidget(row, 2, button)
                combo.currentIndexChanged.connect(lambda _index, control=combo, action=button, kind=stream.kind:
                                                  action.setEnabled(control.currentData() not in ('omit', 'copy') and kind in ('video', 'audio')))

    def _streams_edited(self):
        if not self.rendering and self.stream_item:
            tracks = tuple((stream.index, self.tracks.cellWidget(row, 1).currentData())
                           for row, stream in enumerate(self.stream_item.media.streams) if stream.index is not None)
            output = self.stream_output or self.stream_item
            self.streams_changed.emit(output.id, tracks)
            if self.stream_output:
                request = output.options[output.operation].request
                current = dict(tracks)
                profiles = tuple((index, profile) for index, profile in request.stream_profiles
                                 if current.get(index) == profile.encoder)
                if profiles != request.stream_profiles:
                    self.stream_profiles_changed.emit(output.id, profiles)

    def _edit_stream(self, stream):
        from media_wrapper.application.conversion_service import profile_for_stream

        output = self.stream_output
        request = output.options[output.operation].request
        encoder = dict(request.tracks).get(stream.index)
        if encoder in (None, 'omit', 'copy'):
            return
        overrides = dict(request.stream_profiles)
        profile = overrides.get(stream.index) or profile_for_stream(request, stream, encoder)
        if stream.kind == 'audio':
            fields = (('bitrate', 'Bitrate (bit/s)', int), ('sample_rate', 'Sample rate (Hz)', int),
                      ('channels', 'Channel count', int), ('channel_layout', 'Channel layout', str))
        else:
            fields = (('codec_profile', 'Codec profile', str), ('level', 'Codec level', str),
                      ('pixel_format', 'Pixel format', str), ('color_space', 'Color matrix', str),
                      ('color_transfer', 'Color transfer', str), ('color_primaries', 'Color primaries', str),
                      ('color_range', 'Color range', str))
        dialog = QDialog(self)
        dialog.setWindowTitle(f'Options · {stream.title or stream.kind} ({stream.index})')
        form = QFormLayout(dialog)
        inputs = {}
        for name, label, parser in fields:
            current = getattr(profile, name)
            inputs[name] = field = QLineEdit('' if current is None else str(current))
            field.setPlaceholderText('Encoder default or source')
            field.setAccessibleName(label)
            form.addRow(label, field)
        error = QLabel()
        error.setProperty('validation', 'error')
        error.setWordWrap(True)
        form.addRow(error)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel |
                                   QDialogButtonBox.StandardButton.Reset)
        form.addRow(actions)

        def save():
            values = {}
            for name, label, parser in fields:
                raw = inputs[name].text().strip()
                try:
                    value = parser(raw) if raw else None
                    if parser is int and value is not None and value <= 0:
                        raise ValueError
                except ValueError:
                    error.setText(f'{label} must be a positive whole number.')
                    inputs[name].setFocus()
                    return
                values[name] = value
            if (updated := replace(profile, **values)) != profile:
                overrides[stream.index] = updated
                self.stream_profiles_changed.emit(output.id, tuple(overrides.items()))
            dialog.accept()

        def reset():
            if stream.index in overrides:
                del overrides[stream.index]
                self.stream_profiles_changed.emit(output.id, tuple(overrides.items()))
            dialog.accept()

        actions.accepted.connect(save)
        actions.rejected.connect(dialog.reject)
        actions.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(reset)
        dialog.exec()
