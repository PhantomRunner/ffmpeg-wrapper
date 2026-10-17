"""Distribution contracts; native binary execution is scripts/verify_distribution.py."""
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from media_wrapper.infrastructure import process_environment as environment
from media_wrapper.infrastructure.ffmpeg import binary_resolver


def test_sidecar_location_is_next_to_frozen_executable(monkeypatch, tmp_path):
    executable = tmp_path / 'app ü space' / 'MediaWrapper.exe'
    monkeypatch.setattr(binary_resolver.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(binary_resolver.sys, 'executable', str(executable))
    assert binary_resolver.sidecar_directory() == executable.parent / 'ffmpeg/bin'
    assert not binary_resolver.sidecar_directory().exists()


def test_source_sidecar_is_explicit_and_missing_directory_does_not_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(binary_resolver.sys, 'frozen', False, raising=False)
    assert binary_resolver.sidecar_directory().name == 'bin'
    monkeypatch.setattr(binary_resolver.shutil, 'which', lambda *_: pytest.fail('Unexpected PATH fallback'))
    with pytest.raises(FileNotFoundError):
        binary_resolver.resolve('bundled', tmp_path / 'missing')


@pytest.mark.parametrize('original', [None, '/original/lib'])
def test_frozen_linux_children_restore_library_environment(monkeypatch, original):
    monkeypatch.setattr(environment.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(environment.sys, 'platform', 'linux')
    monkeypatch.setenv('LD_LIBRARY_PATH', '/frozen/lib')
    monkeypatch.delenv('LD_LIBRARY_PATH_ORIG', raising=False)
    if original:
        monkeypatch.setenv('LD_LIBRARY_PATH_ORIG', original)
    result = environment.external_environment()
    assert result.get('LD_LIBRARY_PATH') == original
    assert os.environ['LD_LIBRARY_PATH'] == '/frozen/lib'


def test_nonfrozen_environment_is_unchanged_copy(monkeypatch):
    monkeypatch.setattr(environment.sys, 'frozen', False, raising=False)
    assert environment.external_environment() == dict(os.environ)
    assert environment.external_environment() is not os.environ


def test_windows_dll_reset_and_internal_path_filter(monkeypatch, tmp_path):
    import ctypes
    monkeypatch.setattr(environment.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(environment.sys, 'platform', 'win32')
    internal = tmp_path / '_internal'
    external = tmp_path / 'ffmpeg/bin'
    monkeypatch.setattr(environment.sys, '_MEIPASS', str(internal), raising=False)
    monkeypatch.setenv('PATH', os.pathsep.join([str(internal), str(internal / 'Qt/bin'), str(external)]))
    calls = []
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(kernel32=SimpleNamespace(SetDllDirectoryW=lambda arg: calls.append(arg) or 1)), raising=False)
    environment.initialize_external_processes()
    assert calls == [None]
    assert environment.external_environment()['PATH'] == str(external)
    monkeypatch.setattr(ctypes.windll.kernel32, 'SetDllDirectoryW', lambda _: 0)
    with pytest.raises(OSError):
        environment.initialize_external_processes()


def test_verifier_refuses_nonempty_directory_before_starting_qt(tmp_path):
    from media_wrapper.ui.installation_verification import verify_installation
    source = tmp_path / 'input.mkv'
    source.touch()
    output = tmp_path / 'out'
    output.mkdir()
    marker = output / 'keep.txt'
    marker.write_text('keep')
    with pytest.raises(ValueError, match='empty'):
        verify_installation(source, output)
    assert marker.read_text() == 'keep'


def test_bundle_recipe_has_no_ffmpeg_collection():
    root = Path(__file__).resolve().parents[1]
    text = (root / 'packaging/MediaWrapper.spec').read_text()
    assert 'COLLECT' in text and 'resources' in text
    assert 'ffmpeg' not in text.lower()
    assert 'shell=True' not in (root / 'scripts/build_distribution.py').read_text()
