"""Convert form: typed choices only, never FFmpeg arguments."""
from pathlib import Path

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from media_wrapper.domain.encoding_presets import PRESETS
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import MediaOperation, PreservationPolicy
from media_wrapper.domain.remux import Container
from media_wrapper.ui.widgets.controls import ActionButton, PanelHeader


class EncodingView(QScrollArea):
    def __init__(self, title: str = 'Convert') -> None:
        super().__init__()
        self.title = title
        self.setWidgetResizable(True)
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.addWidget(PanelHeader(title, 'Configure output, stream choices and encoding settings.'))
        self.source = QLabel('Inspect a source first.')
        self.source.setWordWrap(True)
        layout.addWidget(self.source)
        self.form = QWidget()
        form = QFormLayout(self.form)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.hardware_mode = QComboBox()
        self.hardware_mode.addItems(['CPU', 'GPU', 'Auto'])
        self.gpu_encoder = QComboBox()
        self.gpu_encoder.addItem('auto')
        self.hardware_status = QLabel('Scan and test GPUs in Settings. CPU is the default.')
        self.hardware_status.setWordWrap(True)
        self.hardware_mode.currentIndexChanged.connect(self.clear_preview)
        self.gpu_encoder.currentIndexChanged.connect(self.clear_preview)
        form.addRow('Processing', self.hardware_mode)
        form.addRow('Tested GPU encoder', self.gpu_encoder)
        form.addRow(self.hardware_status)
        self.presets = QComboBox()
        self.presets.addItems([p.name for p in PRESETS])
        self.apply_preset_button = ActionButton('Apply editable preset')
        self.apply_preset_button.clicked.connect(self.apply_preset)
        form.addRow('Starting point', self.presets)
        form.addRow(self.apply_preset_button)
        self.import_profile_button = ActionButton('Import profile…')
        self.export_profile_button = ActionButton('Save / export profile…')
        form.addRow(self.import_profile_button, self.export_profile_button)
        self.container = QComboBox()
        self.container.addItems(['Matroska', 'MP4'])
        self.destination = QLineEdit()
        self.browse = ActionButton('Choose output…')
        form.addRow('Container', self.container)
        form.addRow('New destination', self.destination)
        form.addRow(self.browse)
        self.tracks = QTableWidget(0, 2)
        self.tracks.setHorizontalHeaderLabels(['Source track', 'Action / CPU encoder'])
        self.tracks.horizontalHeader().setStretchLastSection(True)
        self.tracks.setMinimumHeight(120)
        self.tracks.setMaximumHeight(150)
        self.tracks.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        form.addRow(self.tracks)
        self.advanced_toggle = QCheckBox('Advanced settings and batch')
        form.addRow(self.advanced_toggle)
        self.advanced = QWidget()
        form.addRow(self.advanced)
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        self.advanced.hide()
        form = QFormLayout(self.advanced)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.track_order = QLineEdit()
        self.track_order.setPlaceholderText('Optional selected indices in output order, e.g. 2,0,3')
        self.metadata_policy, self.chapter_policy = QComboBox(), QComboBox()
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
        form.addRow('Video width', self.video_width)
        form.addRow('Video height', self.video_height)
        form.addRow('Video FPS', self.fps)
        form.addRow('AAC bitrate (kb/s)', self.audio_bitrate)
        self.mode = QComboBox()
        self.mode.addItems(['default', 'quality', 'bitrate', 'target'])
        self.mode.setCurrentText('quality' if title == 'Compress' else 'default')
        self.crf = QSpinBox()
        self.crf.setRange(0, 51)
        self.crf.setValue(23)
        self.video_bitrate = QSpinBox()
        self.video_bitrate.setRange(32, 200000)
        self.video_bitrate.setValue(2000)
        self.preset = QComboBox()
        self.preset.addItems(['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'])
        self.preset.setCurrentText('medium')
        self.audio_mode = QComboBox()
        self.audio_mode.addItems(['bitrate', 'quality'])
        self.audio_quality = QSpinBox()
        self.audio_quality.setRange(1, 5)
        self.audio_quality.setValue(2)
        self.target_size = QSpinBox()
        self.target_size.setRange(1, 1000000)
        self.target_size.setValue(100)
        self.target_size.valueChanged.connect(self.clear_preview)
        form.addRow('Video rate control', self.mode)
        form.addRow('Approximate target (MiB, H.264 two-pass)', self.target_size)
        form.addRow('H.264/H.265 CRF (lower = higher quality)', self.crf)
        form.addRow('Video bitrate (kb/s)', self.video_bitrate)
        form.addRow('Encoder speed preset', self.preset)
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
        self.batch_button = ActionButton('Add selected Files rows as batch')
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
        self._encoders: list[QComboBox] = []
        for widget in (self.destination, self.fps):
            widget.textChanged.connect(self.preview.clear)
        for widget in (self.video_width, self.video_height, self.audio_bitrate):
            widget.valueChanged.connect(self.preview.clear)
        self.container.currentIndexChanged.connect(self.preview.clear)
        self.update_options()

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
        self.container.setCurrentIndex(0 if preset.container == Container.MATROSKA else 1)
        if self.destination.text():
            self.destination.setText(str(Path(self.destination.text()).with_suffix('.mp4' if preset.container == Container.MP4 else '.mkv')))
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
        self.container.setCurrentIndex(0 if request.container == Container.MATROSKA else 1)
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
        if hasattr(self, 'preview'):
            self.preview.clear()

    def update_options(self) -> None:
        self.target_size.setEnabled(self.mode.currentText() == 'target')
        self.crf.setEnabled(self.mode.currentText() == 'quality')
        self.video_bitrate.setEnabled(self.mode.currentText() == 'bitrate')
        self.preset.setEnabled(self.mode.currentText() != 'default')
        self.audio_bitrate.setEnabled(self.audio_mode.currentText() == 'bitrate')
        self.audio_quality.setEnabled(self.audio_mode.currentText() == 'quality')
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
        self.source.setText(f'{self.title}: {media.path}' if media else 'Inspect a source first.')
        self.tracks.setRowCount(len(media.streams) if media else 0)
        self._encoders.clear()
        if media is None:
            self.destination.clear()
            return
        suffix = '.mkv' if self.container.currentIndex() == 0 else '.mp4'
        self.destination.setText(str(media.path.with_name(media.path.stem + '_' + self.title.lower() + suffix)))
        for row, stream in enumerate(media.streams):
            self.tracks.setItem(row, 0, QTableWidgetItem(f'{stream.index}: {stream.kind} / {stream.codec}'))
            combo = QComboBox()
            options = {'video': ['libx264', 'libx265', 'ffv1'], 'audio': ['aac', 'pcm_s16le'],
                       'subtitle': ['mov_text', 'srt', 'ass']}.get(stream.kind, [])
            combo.addItems(['copy', 'omit', *options])
            combo.setCurrentText({'video': 'libx264', 'audio': 'aac'}.get(stream.kind, 'copy'))
            combo.currentIndexChanged.connect(self.preview.clear)
            self.tracks.setCellWidget(row, 1, combo)
            self._encoders.append(combo)

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
                                 Container.MATROSKA if self.container.currentIndex() == 0 else Container.MP4,
                                 tuple(tracks), self.video_width.value() or None, self.video_height.value() or None,
                                 self.fps.text(), self.audio_bitrate.value() * 1000,
                                 self.mode.currentText(), self.crf.value(), self.video_bitrate.value() * 1000,
                                 self.preset.currentText(), self.audio_quality.value() if self.audio_mode.currentText() == 'quality' else None,
                                 MediaOperation.COMPRESS if self.title == 'Compress' else MediaOperation.CONVERT,
                                 self.target_size.value() * 1024 * 1024 if self.mode.currentText() == 'target' else None,
                                 self.hardware_mode.currentText(), self.gpu_encoder.currentText(),
                                 tuple(int(i.strip()) for i in self.track_order.text().split(',')) if self.track_order.text().strip() else (),
                                 PreservationPolicy(self.metadata_policy.currentText()), PreservationPolicy(self.chapter_policy.currentText()), self.custom_arguments.text())
