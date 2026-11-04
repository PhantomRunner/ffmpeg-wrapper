"""One scoped inspector for all operations; controls emit typed field patches."""
from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
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


class ParameterField(QWidget):
    reset_requested = Signal()

    def __init__(self, title, control, hint='', parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        row = QHBoxLayout()
        self.label = QLabel(title)
        self.label.setWordWrap(True)
        self.label.setBuddy(control)
        self.label.setMinimumWidth(90)
        control.setAccessibleName(title)
        self.control = control
        row.addWidget(self.label, 2)
        row.addWidget(control, 4)
        reset = ActionButton('↺')
        reset.setAccessibleName(f'Reset {title}')
        reset.setToolTip(f'Reset {title} in the declared edit scope')
        reset.setFixedWidth(30)
        reset.clicked.connect(self.reset_requested)
        row.addWidget(reset)
        layout.addLayout(row)
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

    def show_error(self, text):
        self.error.setText(text)
        self.error.setVisible(bool(text))


class SettingsInspector(QScrollArea):
    field_changed = Signal(str, object)
    scope_changed = Signal(object)
    reset_field = Signal(str)
    reset_all = Signal()
    preset_requested = Signal(str)
    streams_changed = Signal(str, object)
    import_profile = Signal()
    export_profile = Signal()
    save_preset = Signal()
    manage_presets = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setMinimumWidth(260)
        self.rendering = False
        self.fields = {}
        self.groups = {}
        self.stream_key = None
        self.stream_item = None
        body = QWidget()
        body.setProperty('role', 'formBody')
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        self.heading = QLabel('Operation settings')
        self.heading.setProperty('role', 'panelTitle')
        layout.addWidget(self.heading)
        self.scope = ReadableComboBox()
        self.scope.setAccessibleName('Edit scope')
        self.scope.currentIndexChanged.connect(self._scope_changed)
        layout.addWidget(self.scope)
        self.scope_note = QLabel()
        self.scope_note.setProperty('role', 'fieldHelp')
        self.scope_note.setWordWrap(True)
        layout.addWidget(self.scope_note)
        self.preset = ReadableComboBox()
        self.preset.setAccessibleName('Operation preset')
        self.preset.currentIndexChanged.connect(self._preset_changed)
        self.preset_field = ParameterField('Preset', self.preset)
        self.preset_field.reset_requested.connect(self.reset_all)
        layout.addWidget(self.preset_field)
        self.config = QWidget()
        self.config_layout = QVBoxLayout(self.config)
        self.config_layout.setContentsMargins(0, 0, 0, 0)
        self.config_layout.setSpacing(12)
        layout.addWidget(self.config)

        self._section('media', 'Media')
        self._combo('container', 'Container', [(s.label, c) for c, s in CONTAINERS.items()], 'media')
        self._combo('video_encoder', 'Video codec', [('Copy', 'copy'), ('H.264', 'libx264'),
                    ('H.265 / HEVC', 'libx265'), ('FFV1', 'ffv1')], 'media')
        self._combo('mode', 'Rate control', [('Encoder default', 'default'), ('Quality (CRF)', 'quality'),
                    ('Bitrate', 'bitrate'), ('Target size (two pass)', 'target')], 'media')
        self._spin('crf', 'Quality (CRF)', 0, 51, 'media', hint='Lower = higher quality. CPU H.264/H.265 only.')
        self._spin('video_bitrate', 'Video bitrate', 32, 200000, 'media', 1000, ' kb/s')
        self._spin('target_size_bytes', 'Target size', 1, 1000000, 'media', 1048576, ' MiB',
                   'Approximate budget: one libx264 video and known-rate audio.')
        self._combo('preset', 'Encoder speed', [(n, n) for n in ('ultrafast', 'superfast', 'veryfast',
                    'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow')], 'media')
        self._combo('hardware_mode', 'Processing', [(n, n) for n in ('CPU', 'GPU', 'Auto')], 'media')
        self._combo('gpu_encoder', 'Tested encoder', [('Auto', 'auto')], 'media')
        self.hardware_note = QLabel('GPU requires a successful runtime test in Settings. Quality and target size use CPU.')
        self.hardware_note.setWordWrap(True)
        self.hardware_note.setProperty('role', 'fieldHelp')
        self.groups['media'][1].addWidget(self.hardware_note)

        self._section('audio', 'Audio')
        self._combo('audio_encoder', 'Audio codec', [('Copy', 'copy'), ('AAC', 'aac'), ('PCM 16-bit', 'pcm_s16le')], 'audio')
        self._combo('audio_mode', 'AAC control', [('Bitrate', 'bitrate'), ('Quality', 'quality')], 'audio')
        self._spin('audio_bitrate', 'Audio bitrate', 8, 512, 'audio', 1000, ' kb/s')
        self._spin('audio_quality', 'AAC quality', 1, 5, 'audio', hint='Higher = higher quality; variable output size.')

        self._section('streams', 'Streams')
        self.stream_note = QLabel('Select one inspected row to map its streams. Stream indices are never copied between files.')
        self.stream_note.setWordWrap(True)
        self.stream_note.setProperty('role', 'fieldHelp')
        self.groups['streams'][1].addWidget(self.stream_note)
        self.tracks = QTableWidget(0, 2)
        self.tracks.setHorizontalHeaderLabels(['Source stream', 'Action'])
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
        browse = ActionButton('Choose folder…')
        browse.clicked.connect(self._browse)
        self.groups['output'][1].addWidget(browse)
        self._line('template', 'Name template', 'output', '{name}_{operation}')
        self.fields['template'].hint.setText('Tokens: {name}, {operation}, {index}, {ext}; {stem} also supported. Extension follows the container.')
        self.fields['template'].hint.show()
        self.auto_number = QCheckBox('Auto-number output conflicts')
        self.auto_number.setToolTip('Choose a new unique filename. Existing files are never replaced.')
        self.auto_number.toggled.connect(lambda value: self._emit('auto_number', value))
        self.groups['output'][1].addWidget(self.auto_number)
        self.output_preview = QLabel('Destination is resolved and checked per file during validation.')
        self.output_preview.setTextFormat(Qt.TextFormat.PlainText)
        self.output_preview.setWordWrap(True)
        self.output_preview.setProperty('role', 'fieldHelp')
        self.groups['output'][1].addWidget(self.output_preview)

        self._section('advanced', 'Advanced')
        self._spin('width', 'Width', 0, 16384, 'advanced', suffix=' px', hint='0 = keep original; provide both even dimensions to resize.')
        self._spin('height', 'Height', 0, 16384, 'advanced', suffix=' px')
        self._line('fps', 'Frame rate', 'advanced', 'Keep original, or 30000/1001')
        self._line('track_order', 'Stream order', 'advanced', 'Per-file indices, e.g. 2,0,3')
        self._line('custom_arguments', 'Extra options', 'advanced', '-threads 2 -max_muxing_queue_size 1024')
        self.profile_import = ActionButton('Import profile…')
        self.profile_export = ActionButton('Export profile…')
        self.profile_import.clicked.connect(self.import_profile)
        self.profile_export.clicked.connect(self.export_profile)
        self.groups['advanced'][1].addWidget(self.profile_import)
        self.groups['advanced'][1].addWidget(self.profile_export)
        for title, signal in (('Save named preset…', self.save_preset), ('Manage presets…', self.manage_presets),
                              ('Reset overrides', self.reset_all)):
            button = ActionButton(title)
            button.clicked.connect(signal)
            self.config_layout.addWidget(button)
        layout.addStretch()

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
        control.editingFinished.connect(lambda: self._emit(name, control.text()))

    def _emit(self, name, value):
        if self.rendering or value is MIXED:
            return
        if name == 'audio_mode':
            name, value = 'audio_quality', 2 if value == 'quality' else None
        if name in ('metadata_policy', 'chapter_policy'):
            value = PreservationPolicy(value)
        if name == 'container':
            value = Container(value)
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
            self.heading.setText(draft.operation.value.title() + ' settings')
            self.scope.clear()
            self.scope.addItem(f'Edit: All included ({sum(i.included for i in draft.items.values())})', EditScope.INCLUDED.value)
            self.scope.addItem(f'Edit: Selected rows ({len(draft.selected)})', EditScope.SELECTED.value)
            self.scope.setCurrentIndex(0 if draft.scope == EditScope.INCLUDED else 1)
            targets = draft.editable()
            waiting = any(not item.inspection or item.inspection.status in (InspectionStatus.PENDING, InspectionStatus.RUNNING)
                          for item in draft.targets())
            self.scope_note.setText('Wait for probing in this scope to finish, or use Selected rows.' if waiting else
                                   f'{len(targets)} inspected file(s) in scope. Only the changed field is applied.')
            self.config.setEnabled(bool(targets) and not waiting)
            self.preset.setEnabled(bool(targets) and not waiting)
            self.preset.clear()
            names = [i.options[draft.operation].preset_name + (' (modified)' if i.options[draft.operation].preset_modified else '') for i in targets]
            self.preset.addItem('Mixed' if names and len(set(names)) > 1 else names[0] if names and names[0] else 'Custom', '')
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
            has_video = any(s.kind == 'video' for item in targets for s in item.media.streams)
            has_audio = any(s.kind == 'audio' for item in targets for s in item.media.streams)
            remux = draft.operation == MediaOperation.REMUX
            self.groups['audio'][0].setVisible(not remux and has_audio)
            self.groups['advanced'][0].setVisible(not remux)
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
                        if value is MIXED:
                            control.setPlaceholderText('Mixed — enter a value to apply')
                visible = True
                if name in ('video_encoder', 'mode', 'crf', 'video_bitrate', 'target_size_bytes', 'preset', 'hardware_mode', 'gpu_encoder'):
                    visible = not remux and has_video
                if name == 'crf':
                    visible = visible and mode == 'quality'
                elif name == 'video_bitrate':
                    visible = visible and mode == 'bitrate'
                elif name == 'target_size_bytes':
                    visible = visible and mode == 'target'
                elif name == 'audio_quality':
                    visible = has_audio and audio_quality is not None
                elif name == 'audio_bitrate':
                    visible = has_audio and (audio_quality is None or audio_quality is MIXED)
                elif name in ('width', 'height', 'fps'):
                    visible = has_video
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
            quality_supported = encoder in ('libx264', 'libx265', MIXED) and hardware != 'GPU'
            self.fields['crf'].control.setEnabled(quality_supported)
            self.fields['crf'].show_error('Quality mode requires CPU H.264/H.265. Select Encoder default or a supported codec.'
                                          if has_video and not remux and mode == 'quality' and not quality_supported else '')
            aac = draft.value('audio_encoder') in ('aac', MIXED)
            for name in ('audio_mode', 'audio_quality', 'audio_bitrate'):
                self.fields[name].setVisible(not remux and has_audio and aac and
                                             (name == 'audio_mode' or name == 'audio_quality' and audio_quality is not None
                                              or name == 'audio_bitrate' and (audio_quality is None or audio_quality is MIXED)))
            auto = draft.value('auto_number')
            self.auto_number.setTristate(auto is MIXED)
            self.auto_number.setCheckState(Qt.CheckState.PartiallyChecked if auto is MIXED else Qt.CheckState.Checked if auto else Qt.CheckState.Unchecked)
            item = draft.items.get(draft.selected[0]) if len(draft.selected) == 1 else None
            item = item if item and item.inspected else None
            self._render_streams(item, draft.operation, capabilities)
        finally:
            self.rendering = False

    def _render_streams(self, item, operation, capabilities):
        request = item.options[operation].request if item else None
        key = (item.id if item else None, request.tracks if request else (), operation,
               capabilities.build.identity if capabilities else None)
        self.tracks.setVisible(item is not None)
        self.stream_note.setText(f'Stream mapping: {item.path.name} only. Select/omit explicitly.' if item else
                                'Select one inspected row to map its streams. Indices are per file.')
        if key == self.stream_key:
            return
        self.stream_key, self.stream_item = key, item
        self.tracks.setRowCount(len(item.media.streams) if item else 0)
        for row, stream in enumerate(item.media.streams if item else ()):
            cell = QTableWidgetItem(f'{stream.index}: {stream.kind} / {stream.codec} / {stream.language or "und"}')
            cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.tracks.setItem(row, 0, cell)
            combo = ReadableComboBox()
            combo.addItem('Omit', 'omit')
            if stream.index is not None:
                combo.addItem('Copy', 'copy')
                if operation != MediaOperation.REMUX:
                    for encoder, (kind, _) in ENCODERS.items():
                        if kind == stream.kind and encoder not in GPU_ENCODERS and (not capabilities or encoder in capabilities.build.encoders):
                            combo.addItem(encoder, encoder)
            value = dict(request.tracks).get(stream.index, 'omit')
            if combo.findData(value) < 0:
                combo.addItem(value + ' (unavailable)', value)
            combo.setCurrentIndex(combo.findData(value))
            self.tracks.setCellWidget(row, 1, combo)
            combo.currentIndexChanged.connect(self._streams_edited)

    def _streams_edited(self):
        if not self.rendering and self.stream_item:
            tracks = tuple((stream.index, self.tracks.cellWidget(row, 1).currentData())
                           for row, stream in enumerate(self.stream_item.media.streams) if stream.index is not None)
            self.streams_changed.emit(self.stream_item.id, tracks)
