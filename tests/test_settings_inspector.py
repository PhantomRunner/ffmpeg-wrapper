from PySide6.QtWidgets import QApplication
from test_draft import draft_pair

from media_wrapper.domain.draft import EditScope
from media_wrapper.domain.operations import MediaOperation
from media_wrapper.domain.remux import Container
from media_wrapper.ui.settings_inspector import SettingsInspector


def test_mixed_field_edit_preserves_other_values_and_remux_has_no_encoder(tmp_path):
    app = QApplication.instance() or QApplication([])
    draft, (a, b) = draft_pair(tmp_path)
    draft.operation = MediaOperation.COMPRESS
    draft.patch('crf', 30, (a.id,))
    inspector = SettingsInspector()
    inspector.field_changed.connect(draft.patch)
    inspector.render(draft)
    quality = inspector.fields['crf'].control
    assert quality.value() == quality.minimum()
    inspector.fields['audio_bitrate'].control.setValue(192)
    assert a.options[draft.operation].request.crf == 30
    assert b.options[draft.operation].request.crf == 23
    container = inspector.fields['container'].control
    container.setCurrentIndex(container.findData(Container.MP4))
    assert a.options[draft.operation].request.container is Container.MP4
    draft.operation = MediaOperation.REMUX
    inspector.render(draft)
    assert inspector.fields['crf'].isHidden()
    assert inspector.fields['video_encoder'].isHidden()
    assert inspector.groups['advanced'][0].isHidden()
    draft.scope = EditScope.SELECTED
    draft.selected = ()
    inspector.render(draft)
    assert not inspector.config.isEnabled()
    inspector.close()
    app.processEvents()


def test_stream_change_is_explicitly_per_file(tmp_path):
    app = QApplication.instance() or QApplication([])
    draft, (a, b) = draft_pair(tmp_path)
    draft.selected = (b.id,)
    inspector = SettingsInspector()
    seen = []
    inspector.streams_changed.connect(lambda item_id, tracks: seen.append((item_id, tracks)))
    inspector.render(draft)
    inspector.tracks.cellWidget(0, 1).setCurrentIndex(0)
    assert seen == [(b.id, ((3, 'omit'),))]
    assert a.options[draft.operation].request.tracks == ((0, 'copy'),)
    inspector.close()
    app.processEvents()
