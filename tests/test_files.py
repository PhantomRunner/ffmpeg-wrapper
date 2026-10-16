"""Selection validation and stale-source prevention."""
from pathlib import Path

import pytest

from media_wrapper.application.errors import ApplicationError
from media_wrapper.application.file_service import validate_files
from media_wrapper.ui.view_model import DesktopViewModel


def test_normalize_deduplicate_and_reject_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'clip ü.wav').touch()
    assert validate_files([Path('clip ü.wav'), tmp_path/'clip ü.wav']) == (tmp_path/'clip ü.wav',)
    with pytest.raises(ApplicationError, match='existing media file'):
        validate_files([tmp_path])


def test_selection_changes_and_clear_invalidate_inspected_source(tmp_path):
    first, second = tmp_path/'first.wav', tmp_path/'second.wav'
    first.touch()
    second.touch()
    model = DesktopViewModel()
    model.add_files([first, second, first])
    assert model.state.files == (first, second)
    model.state.source = first
    model.select_file(second)
    assert model.state.source is None
    model.state.source = second
    model.clear_files()
    assert not model.state.files
    assert model.state.current_file is None
    assert model.state.source is None


def test_invalid_add_is_atomic_and_busy_selection_is_preserved(tmp_path):
    good = tmp_path/'good.wav'
    good.touch()
    model = DesktopViewModel()
    model.add_files([good, tmp_path/'missing'])
    assert not model.state.files
    assert 'existing media file' in model.state.output
    model.add_files([good])
    model.state.busy = True
    model.clear_files()
    model.select_file(None)
    assert model.state.files == (good,)
    assert model.state.current_file == good
