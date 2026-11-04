from pathlib import Path
from threading import Event

from media_wrapper.application.import_service import discover_sources
from media_wrapper.domain.draft import MIXED, DraftState, EditScope
from media_wrapper.domain.inspection import InspectionRecord, InspectionStatus
from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.domain.operations import MediaOperation


def draft_pair(tmp_path):
    draft = DraftState()
    items = draft.add((tmp_path / 'a.mkv', tmp_path / 'b.mkv'))
    for item, index in zip(items, (0, 3), strict=True):
        media = MediaFile(item.path, streams=(MediaStream(index, 'video', 'h264'),))
        draft.inspected(InspectionRecord(item.path, InspectionStatus.COMPLETED, media))
    return draft, items


def test_scope_selection_inclusion_and_field_patch_are_independent(tmp_path):
    draft, (a, b) = draft_pair(tmp_path)
    draft.operation = MediaOperation.COMPRESS
    draft.selected = (a.id,)
    draft.patch('crf', 29)
    assert [i.options[draft.operation].request.crf for i in (a, b)] == [29, 29]
    draft.include(a.id, False)
    draft.scope = EditScope.SELECTED
    draft.patch('crf', 20)
    draft.scope = EditScope.INCLUDED
    assert draft.value('crf') == 29
    draft.include(a.id, True)
    assert draft.value('crf') is MIXED
    before = a.options[draft.operation].request
    draft.patch('audio_bitrate', 192000)
    assert a.options[draft.operation].request.crf == before.crf == 20
    assert a.options[draft.operation].request.tracks == ((0, 'libx264'),)
    assert b.options[draft.operation].request.tracks == ((3, 'libx264'),)
    draft.operation = MediaOperation.REMUX
    assert a.options[draft.operation].request.tracks == ((0, 'copy'),)
    draft.operation = MediaOperation.COMPRESS
    assert a.options[draft.operation].request.crf == 20


def test_empty_scope_removed_probe_and_duplicate_import(tmp_path):
    draft, (a, b) = draft_pair(tmp_path)
    assert not draft.add((a.path,))
    draft.scope = EditScope.SELECTED
    revision = draft.revision
    draft.patch('crf', 5)
    assert draft.revision == revision and draft.value('crf') is None
    draft.remove((b.id,))
    draft.inspected(InspectionRecord(b.path, InspectionStatus.FAILED, error='late'))
    assert b.id not in draft.items


def test_recursive_import_deduplicates_and_does_not_follow_directory_symlinks(tmp_path):
    folder = tmp_path / 'input'
    folder.mkdir()
    (folder / 'clip.mkv').touch()
    (folder / 'sub').mkdir()
    (folder / 'sub' / 'audio.wav').touch()
    (folder / 'loop').symlink_to(folder, target_is_directory=True)
    result = discover_sources((folder, folder / 'clip.mkv', tmp_path / 'missing'), Event())
    assert len(result.paths) == 2 and result.errors
    assert all(p.is_absolute() for p in result.paths)
    event = Event()
    event.set()
    assert discover_sources((Path('/does-not-exist'),), event).paths == ()
