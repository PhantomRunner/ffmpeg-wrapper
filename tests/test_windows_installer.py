import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from media_wrapper.infrastructure.installation_guard import MUTEX_NAME

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('windows_installer_builder', ROOT / 'scripts/build_windows_installer.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_native_payload_checksums_are_checked_before_compiling(tmp_path):
    bundle = tmp_path / 'Windows payload with spaces'
    bundle.mkdir()
    executable = bundle / 'MediaWrapper.exe'
    executable.write_bytes(b'test payload')
    manifest = {'MediaWrapper.exe': hashlib.sha256(executable.read_bytes()).hexdigest()}
    (bundle / 'SHA256SUMS.json').write_text(json.dumps(manifest))
    info = {'platform': 'Windows-11', 'ffmpeg_bundled': False}
    (bundle / 'build-info.json').write_text(json.dumps(info))
    assert builder.verify_payload(bundle) == info
    executable.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='checksum'):
        builder.verify_payload(bundle)


def test_installer_preserves_user_data_and_never_forces_application_close(tmp_path):
    recipe = (ROOT / 'packaging/MediaWrapper.iss').read_text()
    assert 'PrivilegesRequired=lowest' in recipe
    assert 'CloseApplications=no' in recipe and 'RestartApplications=no' in recipe
    assert 'AppMutex=' + MUTEX_NAME in recipe
    assert '[UninstallDelete]' not in recipe
    args = builder.compiler_arguments(tmp_path / 'ISCC.exe', tmp_path / 'payload with spaces',
                                      tmp_path / 'output dir', 'candidate', '0.1.0', tmp_path / 'app.ico')
    assert len(args) == 7 and '/DPayloadDir=' + str((tmp_path / 'payload with spaces').resolve()) in args
    pin = json.loads((ROOT / 'packaging/windows-installer-tools.json').read_text())
    assert pin['version'] == '7.1.1' and len(pin['sha256']) == 64
    assert pin['url'].startswith('https://github.com/jrsoftware/issrc/releases/')


def test_changed_cached_compiler_is_preserved_and_never_executed(tmp_path, monkeypatch):
    pin = {'name': 'compiler.exe', 'sha256': '0' * 64, 'url': 'https://example.invalid/not-used'}
    cached = tmp_path / pin['name']
    cached.write_bytes(b'preserve')
    calls = []
    monkeypatch.setattr(builder.subprocess, 'run', lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError, match='checksum'):
        builder.prepare_compiler(tmp_path, pin)
    assert cached.read_bytes() == b'preserve' and not calls
