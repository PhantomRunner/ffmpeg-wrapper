"""Keyboard-accessible processing help; descriptions do not change validation policy."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.ui.theme import apply_theme

# Definition, impact, recommended use, and limitations for the supported UI.
HELP = {
    'container': ('Container', 'The file format packages selected streams. It affects player compatibility, not quality by itself. Choose a format your player accepts. Every stream must be compatible; changing the extension alone does not convert codecs.'),
    'destination': ('Output naming', 'The output is a new file. Choose an existing writable folder and the extension required by the container. Use a distinct name to keep the source. Existing files and source replacement are refused; execution checks again.'),
    'tracks': ('Streams and codecs', 'Each selected video, audio or subtitle stream is mapped separately. Copy preserves encoded data and is fast; encoding trades time and possible quality loss for size or compatibility. Omit explicitly removes a stream. Copy cannot resize or change FPS; unsupported combinations are blocked.'),
    'mode': ('Rate control', 'Quality controls visual fidelity with variable output size. Bitrate budgets data per second. Target size estimates a bitrate from duration. Use quality for fidelity, bitrate for delivery constraints and target for a size budget. Estimates are not guarantees; target mode supports the validated two-pass H.264 workflow.'),
    'crf': ('Quality (CRF)', 'CRF controls quality for supported H.264/H.265 encoding. Lower means higher quality and usually more bytes. Use it when exact size is unimportant. This UI validates CRF 0–51 for H.264/H.265; these are not universal CQ ranges for other encoders. Stream copy ignores quality settings; selected-build validation remains authoritative.'),
    'video_bitrate': ('Video bitrate', 'Kilobits per second budget video data. Higher rates usually increase size and preserve more detail. Use bitrate for delivery limits. Quality varies with content; bitrate is not an exact file-size guarantee and requires a supported encoder.'),
    'audio_bitrate': ('Audio bitrate', 'Kilobits per second budget encoded AAC audio. Higher rates usually increase quality and size. Use for predictable audio bandwidth. The control applies to supported AAC encoding, not copied audio; channels and content affect quality.'),
    'target_size': ('Target size', 'MiB is a requested output-size budget used to estimate bitrate from duration and overhead. Use when delivery has a size limit. Very small budgets may be invalid; two-pass H.264 is required and the final size can differ.'),
    'preset': ('Encoder speed preset', 'The preset trades encoding time for compression efficiency. Slower settings may produce better quality at a fixed bitrate or smaller files at similar quality. Start with medium, then test. Preset support depends on the selected encoder; speed does not guarantee an exact size.'),
    'presets': ('Starting preset', 'A starting preset fills several editable settings. Use it as a convenient baseline, then review streams, output and quality. Applying one can change multiple choices; it is not proof that your build supports the resulting plan. Validate before processing.'),
    'video_width': ('Resolution', 'Width and height set output pixel dimensions. Reducing resolution can lower size but removes detail. Use for delivery dimensions. This workflow requires both positive even dimensions and a video encoder; exact scaling can change aspect ratio. Keep both original to avoid scaling.'),
    'video_height': ('Resolution', 'Height and width set output pixel dimensions. Lower resolution saves data at a cost in detail. Use dimensions required by the destination. Both must be positive and even for scaling; exact scaling may distort aspect ratio and cannot use stream copy.'),
    'fps': ('Frame rate', 'FPS sets output frames per second, including rational values such as 30000/1001. It changes motion cadence and potentially size. Keep original unless delivery requires conversion. Conversion can duplicate or drop frames and needs encoding; supported values must pass validation.'),
    'hardware_mode': ('Hardware acceleration', 'CPU uses software encoding; GPU uses a tested device encoder; Auto selects according to available capability evidence. GPU can improve throughput with different quality and size tradeoffs. Use only tested encoders for this machine. Listing an encoder does not prove it can run; device initialization is checked again.'),
    'gpu_encoder': ('GPU encoder', 'Select a runtime-tested hardware encoder or Auto. It controls the device-specific encoding implementation. Use a tested option for faster processing. Driver, device and build support vary; options and quality ranges are not interchangeable with CPU encoders.'),
    'audio_mode': ('Audio rate control', 'AAC can use a bitrate budget or quality setting. Bitrate helps bandwidth planning; quality allows size to vary with content. This setting is specific to supported AAC encoding and does not change copied audio.'),
    'audio_quality': ('AAC quality', 'The supported AAC quality scale is 1–5, with higher values requesting higher quality. Use when audio size may vary. This is not the video CRF direction or a universal audio codec scale; actual size depends on content.'),
    'track_order': ('Stream order', 'Explicit stream indices set the order in the output. Use when a player expects a particular track first. List every selected index exactly once; this does not select or convert streams and indices differ between files.'),
    'metadata_policy': ('Metadata', 'Preserve keeps global and track tags; strip removes them. Preserve when descriptive information matters, strip when it should not be copied. Metadata may contain private text; preservation depends on container support and is verified.'),
    'chapter_policy': ('Chapters', 'Preserve copies chapter markers; strip omits them. Keep chapters for navigation when supported. Some containers cannot preserve chapters and require explicit stripping; validation will not silently discard them.'),
    'batch_folder': ('Batch folder', 'All batch outputs are placed in this folder. Use an existing writable directory separate from sources. An empty value uses the current destination folder; naming collisions block the batch rather than overwrite.'),
    'batch_template': ('Batch filename template', 'Use {stem}, {index} and {ext} to name each output. Include an index to distinguish similar names and {ext} for the container suffix. Only these placeholders are supported; collisions with sources, existing files or queued outputs are refused.'),
    'custom_arguments': ('Advanced arguments', 'A restricted allowlist exposes threads and muxing queue size. Use only for a known processing constraint. This is not a shell command or unrestricted FFmpeg input; ranges and options are checked before execution.'),
}


def install_help(view, names) -> None:
    view.help_buttons = {}
    view.help_shortcuts = []
    for name in names:
        field = getattr(view, name)
        title, body = HELP[name]
        button = QPushButton()
        button.setText('?')
        button.setFixedSize(24, 26)
        button.setAccessibleName(f'Help: {title}')
        button.setToolTip(f'{title}: {body}\nPress F1 in the field for help.')
        field.setToolTip(f'{title}: {body}\nPress F1 for help.')
        button.clicked.connect(lambda checked=False, name=name: show_help(view, name))
        shortcut = QShortcut('F1', field)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(lambda name=name: show_help(view, name))
        view.help_shortcuts.append(shortcut)
        view.help_buttons[name] = button
        parent_layout = field.parentWidget().layout()
        if isinstance(parent_layout, QFormLayout):
            row, _role = parent_layout.getWidgetPosition(field)
            label_item = parent_layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if label_item and isinstance(label_item.widget(), QLabel):
                label = label_item.widget()
                parent_layout.removeWidget(label)
                wrapper = QWidget()
                wrapper.setFixedWidth(112)
                line = QHBoxLayout(wrapper)
                line.setContentsMargins(0, 0, 0, 0)
                line.setSpacing(2)
                label.setMinimumWidth(0)
                label.setMaximumWidth(16777215)
                label.setBuddy(field)
                line.addWidget(label, 1)
                line.addWidget(button)
                parent_layout.setWidget(row, QFormLayout.ItemRole.LabelRole, wrapper)
                continue
        # Spanning stream tables and the Remux form get a compact adjacent help row.
        wrapper = QWidget()
        line = QHBoxLayout(wrapper)
        line.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setBuddy(field)
        line.addWidget(label, 1)
        line.addWidget(button)
        if isinstance(parent_layout, QFormLayout):
            row, _ = parent_layout.getWidgetPosition(field)
            parent_layout.insertRow(row, wrapper)
        else:
            parent_layout.insertWidget(parent_layout.indexOf(field), wrapper)


def show_help(view, name: str) -> None:
    title, body = HELP[name]
    if not hasattr(view, 'help_dialog'):
        view.help_dialog = QDialog(view.window())
        apply_theme(view.help_dialog)
        layout = QVBoxLayout(view.help_dialog)
        view.help_text = QTextBrowser()
        view.help_text.setAccessibleName('Parameter explanation and tradeoffs')
        layout.addWidget(view.help_text)
    dialog = view.help_dialog
    dialog.setWindowTitle('Help — ' + title)
    view.help_text.setPlainText(title + '\n\n' + body)
    screen = view.screen().availableGeometry()
    dialog.resize(min(520, screen.width() - 32), min(280, screen.height() - 32))
    dialog.show()
    geometry = dialog.frameGeometry()
    dialog.move(max(screen.left(), min(geometry.left(), screen.right() - geometry.width())),
                max(screen.top(), min(geometry.top(), screen.bottom() - geometry.height())))
    view.help_text.setFocus()
