"""Convert form: typed choices only, never FFmpeg arguments."""
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.application.conversion_service import ConversionRequest
from media_wrapper.domain.capabilities import CapabilityReport
from media_wrapper.domain.containers import CONTAINERS
from media_wrapper.domain.encoding_presets import PRESETS
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import MediaOperation, PreservationPolicy
from media_wrapper.domain.remux import Container
from media_wrapper.ui.widgets.combo_box import ReadableComboBox
from media_wrapper.ui.widgets.controls import ActionButton, PanelHeader


class EncodingView(QScrollArea):
    estimate_changed = Signal()
    inputs_changed = Signal()

    def __init__(self, title: str = 'Convert') -> None:
        super().__init__()
        self.title = title
        self.setWidgetResizable(True)
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(PanelHeader(title, 'Choose quality or a size budget, then review the estimate.' if title == 'Compress' else 'Choose a format, map streams and set resolution and frame rate.'))
        self.source = QLabel('Inspect a source first.')
        self.source.setWordWrap(True)
        layout.addWidget(self.source)
        self.form = QWidget()
        form = QFormLayout(self.form)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.hardware_mode = ReadableComboBox()
        self.hardware_mode.addItems(['CPU', 'GPU', 'Auto'])
        self.gpu_encoder = ReadableComboBox()
        self.gpu_encoder.addItem('auto')
        self.hardware_status = QLabel('Scan and test GPUs in Settings. CPU is the default.')
        self.hardware_status.setWordWrap(True)
        self.hardware_mode.currentIndexChanged.connect(self.clear_preview)
        self.gpu_encoder.currentIndexChanged.connect(self.clear_preview)
        form.addRow('Processing', self.hardware_mode)
        form.addRow('Tested GPU encoder', self.gpu_encoder)
        form.addRow(self.hardware_status)
        self.presets = ReadableComboBox()
        self.presets.addItems([p.name for p in PRESETS])
        self.apply_preset_button = ActionButton('Apply editable preset')
        self.apply_preset_button.clicked.connect(self.apply_preset)
        form.addRow('Starting point', self.presets)
        form.addRow(self.apply_preset_button)
        self.import_profile_button = ActionButton('Import profile…')
        self.export_profile_button = ActionButton('Save / export profile…')
        form.addRow(self.import_profile_button)
        form.addRow(self.export_profile_button)
        self.container = ReadableComboBox()
        for container, spec in CONTAINERS.items():
            self.container.addItem(f'{spec.label} ({spec.extension})', container.value)
        self.destination = QLineEdit()
        self.browse = ActionButton('Choose output…')
        form.addRow('Container', self.container)
        form.addRow('Output file', self.destination)
        form.addRow(self.browse)
        self.tracks = QTableWidget(0, 2)
        self.tracks.setHorizontalHeaderLabels(['Source track', 'Action / CPU encoder'])
        self.tracks.horizontalHeader().setStretchLastSection(True)
        self.tracks.setMinimumHeight(72)
        self.tracks.setMaximumHeight(150)
        self.tracks.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        form.addRow(self.tracks)
        self.advanced_toggle = QCheckBox('Advanced settings')
        form.addRow(self.advanced_toggle)
        self.advanced = QWidget()
        form.addRow(self.advanced)
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        self.advanced.hide()
        form = QFormLayout(self.advanced)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.track_order = QLineEdit()
        self.track_order.setPlaceholderText('Optional selected indices in output order, e.g. 2,0,3')
        self.metadata_policy, self.chapter_policy = ReadableComboBox(), ReadableComboBox()
        for combo in (self.metadata_policy, self.chapter_policy):
            combo.addItems(['preserve', 'strip'])
            combo.currentIndexChanged.connect(self.clear_preview)
        self.track_order.textChanged.connect(self.clear_preview)
        form.addRow('Explicit output track order', self.track_order)
        form.addRow('Global and track metadata', self.metadata_policy)
        form.addRow('Chapters', self.chapter_policy)
        self.video_width, self.video_height = QSpinBox(), QSpinBox()
        for widget in (self.video_width, self.video_height):
            widget.setRange(0, 16384)
            widget.setSpecialValueText('Keep original')
            widget.setSingleStep(2)
        self.fps = QLineEdit()
        self.fps.setPlaceholderText('Keep original, or e.g. 30000/1001')
        self.audio_bitrate = QSpinBox()
        self.audio_bitrate.setRange(8, 512)
        self.audio_bitrate.setValue(128)
        form.addRow('Width', self.video_width)
        form.addRow('Height', self.video_height)
        form.addRow('Frame rate', self.fps)
        form.addRow('Audio bitrate (kb/s)', self.audio_bitrate)
        self.mode = ReadableComboBox()
        self.mode.addItems(['default', 'quality', 'bitrate', 'target'])
        self.mode.setCurrentText('quality' if title == 'Compress' else 'default')
        self.crf = QSpinBox()
        self.crf.setToolTip('Lower CRF gives higher quality and usually a larger output.')
        self.crf.setRange(0, 51)
        self.crf.setValue(23)
        self.video_bitrate = QSpinBox()
        self.video_bitrate.setRange(32, 200000)
        self.video_bitrate.setValue(2000)
        self.preset = ReadableComboBox()
        self.preset.addItems(['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'])
        self.preset.setCurrentText('medium')
        self.audio_mode = ReadableComboBox()
        self.audio_mode.addItems(['bitrate', 'quality'])
        self.audio_quality = QSpinBox()
        self.audio_quality.setRange(1, 5)
        self.audio_quality.setValue(2)
        self.target_size = QSpinBox()
        self.target_size.setRange(1, 1000000)
        self.target_size.setValue(100)
        self.target_size.valueChanged.connect(self.clear_preview)
        form.addRow('Rate control', self.mode)
        form.addRow('Target size (MiB)', self.target_size)
        form.addRow('Quality (CRF)', self.crf)
        form.addRow('Video bitrate (kb/s)', self.video_bitrate)
        form.addRow('Speed preset', self.preset)
        form.addRow('AAC rate control', self.audio_mode)
        form.addRow('AAC quality (higher = higher quality)', self.audio_quality)
        self.mode.currentIndexChanged.connect(self.update_options)
        self.audio_mode.currentIndexChanged.connect(self.update_options)
        for widget in (self.crf, self.video_bitrate, self.audio_quality):
            widget.valueChanged.connect(self.clear_preview)
        self.preset.currentIndexChanged.connect(self.clear_preview)
        self.custom_arguments = QLineEdit()
        self.custom_arguments.setPlaceholderText('-threads 2 -max_muxing_queue_size 1024')
        self.custom_arguments.setToolTip('Optional: only -threads 1–64 and -max_muxing_queue_size 1–65536. Preview validates these options.')
        self.custom_arguments.textChanged.connect(self.clear_preview)
        form.addRow('Restricted advanced arguments', self.custom_arguments)
        self.batch_folder = QLineEdit()
        self.batch_folder.setPlaceholderText('Output folder (empty = current destination folder)')
        self.batch_template = QLineEdit('{stem}_{index}_encoded{ext}')
        self.batch_button = ActionButton('Queue selected files')
        form.addRow('Batch output folder', self.batch_folder)
        form.addRow('Batch filename template', self.batch_template)
        form.addRow(self.batch_button)
        layout.addWidget(self.form)
        self.note = QLabel('Quality mode gives variable size; lower CRF usually uses more space. Slower presets trade time for efficiency. Bitrate mode targets a rate, not an exact size. Target size estimates overhead and uses two-pass H.264; actual size can differ. Encoders are checked against your FFmpeg build before running. Copy preserves the original stream; Omit removes it explicitly. Scaling uses the exact dimensions entered.')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        buttons = QVBoxLayout()
        self.preview_button = ActionButton('Validate and preview')
        self.run_button = ActionButton('Run', primary=True)
        self.enqueue_button = ActionButton('Add to queue')
        for button in (self.preview_button, self.run_button, self.enqueue_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(100)
        layout.addWidget(self.preview)
        self._media: MediaFile | None = None
        self._encoders: list[ReadableComboBox] = []
        for widget in (self.destination, self.fps):
            widget.textChanged.connect(self.clear_preview)
        for widget in (self.video_width, self.video_height, self.audio_bitrate):
            widget.valueChanged.connect(self.clear_preview)
        self.container.currentIndexChanged.connect(self.container_changed)
        self.arrange_workflow()
        for form_layout in (self.form.layout(), self.advanced.layout()):
            form_layout.setContentsMargins(0, 0, 0, 0)
            form_layout.setVerticalSpacing(6)
            form_layout.setHorizontalSpacing(8)
            form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for row in range(form_layout.rowCount()):
                label = form_layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if label and isinstance(label.widget(), QLabel):
                    label.widget().setWordWrap(True)
                    label.widget().setFixedWidth(112)
        self.update_options()

    def arrange_workflow(self) -> None:
        main, advanced = self.form.layout(), self.advanced.layout()

        def move(widget: QWidget, source: QFormLayout, target: QFormLayout, row: int) -> None:
            items = source.takeRow(widget)
            if items.labelItem:
                target.insertRow(row, items.labelItem.widget(), items.fieldItem.widget())
            else:
                target.insertRow(row, items.fieldItem.widget())

        # Promote the controls that define this operation, retaining request bindings.
        promoted = ((self.mode, self.crf, self.video_bitrate, self.target_size,
                     self.preset, self.audio_bitrate) if self.title == 'Compress' else
                    (self.video_width, self.video_height, self.fps))
        for widget in promoted:
            row, _ = main.getWidgetPosition(self.advanced_toggle)
            move(widget, advanced, main, row)
        if self.title == 'Compress':
            move(self.tracks, main, advanced, 0)
            self.advanced_toggle.setText('Streams and advanced')
            self.advanced_toggle.setToolTip('Streams, format adjustments, processing, profiles and batch settings')
        self.estimate = QLabel()
        self.estimate.setWordWrap(True)
        self.estimate.setAccessibleName('Estimated output size')
        row, _ = main.getWidgetPosition(self.advanced_toggle)
        main.insertRow(row, self.estimate)
        self.estimate.setVisible(self.title == 'Compress')
        for widget in (self.hardware_mode, self.gpu_encoder, self.hardware_status,
                       self.import_profile_button, self.export_profile_button):
            move(widget, main, advanced, advanced.rowCount())
        if self.title == 'Convert':
            for widget in (self.presets, self.apply_preset_button):
                move(widget, main, advanced, advanced.rowCount())
        else:
            for row, widget in enumerate((self.mode, self.crf, self.video_bitrate,
                                          self.target_size, self.preset, self.estimate)):
                move(widget, main, main, row)
        advanced.addRow(self.note)
        advanced.addRow('Validated command', self.preview)
        for widget in (self.mode, self.audio_mode):
            widget.currentIndexChanged.connect(self.update_estimate)
        for widget in (self.video_bitrate, self.audio_bitrate, self.target_size):
            widget.valueChanged.connect(self.update_estimate)

    def update_estimate(self) -> None:
        if not hasattr(self, 'estimate'):
            return
        from media_wrapper.application.size_estimate import estimate_output
        try:
            text = estimate_output(self._media, self.request()) if self._media else 'Inspect a source to estimate output size.'
        except ValueError as error:
            text = str(error)
        self.estimate.setText(text)
        self.estimate_changed.emit()

    def container_changed(self) -> None:
        from media_wrapper.ui.output_paths import suggest_output_path
        container = Container(self.container.currentData())
        self.destination.setText(suggest_output_path(self.destination.text(), container))
        self.clear_preview()

    def set_capabilities(self, report: CapabilityReport | None) -> None:
        names = ['auto', *sorted(report.working())] if report else ['auto']
        if names != [self.gpu_encoder.itemText(i) for i in range(self.gpu_encoder.count())]:
            previous = self.gpu_encoder.currentText()
            with QSignalBlocker(self.gpu_encoder):
                self.gpu_encoder.clear()
                self.gpu_encoder.addItems(names)
                self.gpu_encoder.setCurrentText(previous if previous in names else 'auto')
            self.clear_preview()
        self.hardware_status.setText('GPU/Auto uses only runtime-tested matching encoders. GPU supports default/bitrate modes; quality/two-pass stays CPU.' if len(names) > 1 else 'No runtime-tested GPU is available. CPU remains selectable; scan/test in Settings.')

    def apply_preset(self) -> None:
        if self._media is None:
            return
        preset = PRESETS[self.presets.currentIndex()]
        self.container.setCurrentIndex(self.container.findData(preset.container))
        self.container_changed()
        self.mode.setCurrentText('quality' if preset.video_encoder else 'default')
        self.crf.setValue(preset.crf)
        self.preset.setCurrentText(preset.speed)
        self.audio_mode.setCurrentText('bitrate')
        self.audio_bitrate.setValue(preset.audio_bitrate // 1000)
        self.video_width.setValue(0)
        self.video_height.setValue(0)
        self.fps.clear()
        for stream, combo in zip(self._media.streams, self._encoders, strict=True):
            encoder = ('aac' if stream.kind == 'audio' else 'omit') if preset.video_encoder is None else (
                preset.video_encoder if stream.kind == 'video' else 'aac' if stream.kind == 'audio' else 'copy')
            combo.setCurrentText(encoder)
        self.note.setText('Preset applied. Review and edit every track and setting. Audio-only presets explicitly omit non-audio tracks. Encoder availability and container compatibility are checked before execution.')
        self.clear_preview()

    def apply_request(self, request: ConversionRequest) -> None:
        self.container.setCurrentIndex(self.container.findData(request.container))
        self.destination.setText(str(request.destination))
        self.video_width.setValue(request.width or 0)
        self.video_height.setValue(request.height or 0)
        self.fps.setText(request.fps)
        self.audio_bitrate.setValue(request.audio_bitrate // 1000)
        self.mode.setCurrentText(request.mode)
        self.crf.setValue(request.crf)
        self.video_bitrate.setValue(request.video_bitrate // 1000)
        self.preset.setCurrentText(request.preset)
        self.audio_mode.setCurrentText('quality' if request.audio_quality is not None else 'bitrate')
        self.audio_quality.setValue(request.audio_quality or 2)
        self.target_size.setValue((request.target_size_bytes or 104857600) // 1048576)
        self.custom_arguments.setText(request.custom_arguments)
        self.track_order.setText(','.join(str(i) for i in request.track_order))
        self.metadata_policy.setCurrentText(request.metadata_policy.value)
        self.chapter_policy.setCurrentText(request.chapter_policy.value)
        self.hardware_mode.setCurrentText(request.hardware_mode)
        self.gpu_encoder.setCurrentText(request.gpu_encoder)
        choices = dict(request.tracks)
        for stream, combo in zip(self._media.streams, self._encoders, strict=True):
            combo.setCurrentText(choices.get(stream.index, 'omit'))
        self.clear_preview()

    def clear_preview(self) -> None:
        self.inputs_changed.emit()
        if hasattr(self, 'preview'):
            self.preview.clear()
        self.update_estimate()

    def update_options(self) -> None:
        self.target_size.setEnabled(self.mode.currentText() == 'target')
        self.crf.setEnabled(self.mode.currentText() == 'quality')
        self.video_bitrate.setEnabled(self.mode.currentText() == 'bitrate')
        self.preset.setEnabled(self.mode.currentText() != 'default')
        self.audio_bitrate.setEnabled(self.audio_mode.currentText() == 'bitrate')
        self.audio_quality.setEnabled(self.audio_mode.currentText() == 'quality')
        if self.title == 'Compress':
            for widget, mode in ((self.crf, 'quality'), (self.video_bitrate, 'bitrate'),
                                 (self.target_size, 'target')):
                self.form.layout().setRowVisible(widget, self.mode.currentText() == mode)
        self.clear_preview()

    def set_media(self, media: MediaFile | None, busy: bool) -> None:
        self.form.setEnabled(not busy and media is not None)
        for button in (self.preview_button, self.run_button, self.enqueue_button):
            button.setEnabled(not busy and media is not None)
        if media is self._media:
            return
        self._media = media
        self.track_order.clear()
        self.preview.clear()
        self.source.setText(media.path.name if media else 'Inspect a source first.')
        self.source.setToolTip(str(media.path) if media else '')
        count = len(media.streams) if media else 0
        self.tracks.setRowCount(count)
        self.tracks.setFixedHeight(min(150, max(72, self.tracks.horizontalHeader().height()
                                              + count * self.tracks.verticalHeader().defaultSectionSize() + 4)))
        self._encoders.clear()
        if media is None:
            self.destination.clear()
            self.update_estimate()
            return
        suffix = CONTAINERS[Container(self.container.currentData())].extension
        self.destination.setText(str(media.path.with_name(media.path.stem + '_' + self.title.lower() + suffix)))
        for row, stream in enumerate(media.streams):
            self.tracks.setItem(row, 0, QTableWidgetItem(f'{stream.index}: {stream.kind} / {stream.codec}'))
            combo = ReadableComboBox()
            options = {'video': ['libx264', 'libx265', 'ffv1'], 'audio': ['aac', 'pcm_s16le'],
                       'subtitle': ['mov_text', 'srt', 'ass']}.get(stream.kind, [])
            combo.addItems(['copy', 'omit', *options])
            combo.setCurrentText({'video': 'libx264', 'audio': 'aac'}.get(stream.kind, 'copy'))
            combo.currentIndexChanged.connect(self.clear_preview)
            self.tracks.setCellWidget(row, 1, combo)
            self._encoders.append(combo)
        self.update_estimate()

    def request(self) -> ConversionRequest:
        if self._media is None or not self.destination.text().strip():
            raise ValueError('Inspect a file and choose a new destination')
        tracks = []
        for stream, combo in zip(self._media.streams, self._encoders, strict=True):
            if stream.index is None:
                if combo.currentText() != 'omit':
                    raise ValueError('Omit tracks with missing indices')
            else:
                tracks.append((stream.index, combo.currentText()))
        return ConversionRequest(Path(self.destination.text()),
                                 Container(self.container.currentData()),
                                 tuple(tracks), self.video_width.value() or None, self.video_height.value() or None,
                                 self.fps.text(), self.audio_bitrate.value() * 1000,
                                 self.mode.currentText(), self.crf.value(), self.video_bitrate.value() * 1000,
                                 self.preset.currentText(), self.audio_quality.value() if self.audio_mode.currentText() == 'quality' else None,
                                 MediaOperation.COMPRESS if self.title == 'Compress' else MediaOperation.CONVERT,
                                 self.target_size.value() * 1024 * 1024 if self.mode.currentText() == 'target' else None,
                                 self.hardware_mode.currentText(), self.gpu_encoder.currentText(),
                                 tuple(int(i.strip()) for i in self.track_order.text().split(',')) if self.track_order.text().strip() else (),
                                 PreservationPolicy(self.metadata_policy.currentText()), PreservationPolicy(self.chapter_policy.currentText()), self.custom_arguments.text())
