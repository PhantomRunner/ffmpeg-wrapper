import hashlib
import importlib.util
import io
import json
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('build_appimage', Path(__file__).parents[1] / 'scripts/build_appimage.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.skipif(__import__('sys').platform != 'linux', reason='Linux AppRun shell launcher')
def test_appdir_checksums_spaces_arguments_and_no_overwrite(tmp_path):
    bundle = tmp_path / 'payload'
    bundle.mkdir()
    executable = bundle / 'MediaWrapper'
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    executable.chmod(0o755)
    (bundle / 'SHA256SUMS.json').write_text(json.dumps({'MediaWrapper': hashlib.sha256(executable.read_bytes()).hexdigest()}))
    icon = tmp_path / 'icon.svg'
    icon.write_text('<svg/>')
    target = tmp_path / 'App Dir ü'
    module.assemble_appdir(bundle, target, icon)
    result = subprocess.run([str(target / 'AppRun'), 'space name', '$literal', 'кириллица'],
                            check=True, text=True, capture_output=True)
    assert result.stdout.splitlines() == ['space name', '$literal', 'кириллица']
    assert (target / '.DirIcon').is_symlink()
    with pytest.raises(ValueError, match='already exists'):
        module.assemble_appdir(bundle, target, icon)
    executable.write_text('corrupt')
    with pytest.raises(ValueError, match='checksum'):
        module.assemble_appdir(bundle, tmp_path / 'bad', icon)


def test_prepare_downloads_verified_tools_atomically_and_reuses_cache(tmp_path, monkeypatch):
    content = b'pinned AppImage tool'
    pins = {'tool': {'name': 'appimagetool', 'sha256': hashlib.sha256(content).hexdigest(),
                     'url': 'https://example.invalid/appimagetool'}}
    requests = []

    def download(request, timeout):
        requests.append(request.full_url)
        return io.BytesIO(content)

    monkeypatch.setattr(module.urllib.request, 'urlopen', download)
    directory = tmp_path / 'tools with spaces'
    result = module.prepare_tools(directory, pins, download=True)
    assert result['tool'].read_bytes() == content
    assert result['tool'].stat().st_mode & 0o100
    assert list(directory.iterdir()) == [result['tool']]
    assert module.prepare_tools(directory, pins, download=True) == result
    assert requests == ['https://example.invalid/appimagetool']


def test_prepare_refuses_existing_mismatched_tools_without_replacing_them(tmp_path, monkeypatch):
    path = tmp_path / 'appimagetool'
    path.write_bytes(b'previous tool')
    pins = {'tool': {'name': path.name, 'sha256': '0' * 64, 'url': 'https://example.invalid/tool'}}
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *args, **kwargs: pytest.fail('Existing tool downloaded again'))
    with pytest.raises(SystemExit, match='Missing or mismatched'):
        module.prepare_tools(tmp_path, pins, download=True)
    assert path.read_bytes() == b'previous tool'


def test_prepare_rejects_changed_download_and_removes_partial_file(tmp_path, monkeypatch):
    pins = {'tool': {'name': 'appimagetool', 'sha256': '0' * 64, 'url': 'https://example.invalid/tool'}}
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *args, **kwargs: io.BytesIO(b'changed upstream asset'))
    with pytest.raises(SystemExit, match='Download checksum mismatch'):
        module.prepare_tools(tmp_path, pins, download=True)
    assert list(tmp_path.iterdir()) == []


def test_prepare_reports_network_errors_and_removes_partial_file(tmp_path, monkeypatch):
    pins = {'tool': {'name': 'appimagetool', 'sha256': '0' * 64, 'url': 'https://example.invalid/tool'}}

    def unavailable(*args, **kwargs):
        raise module.urllib.error.URLError('offline')

    monkeypatch.setattr(module.urllib.request, 'urlopen', unavailable)
    with pytest.raises(SystemExit, match='Could not prepare tool:.*offline'):
        module.prepare_tools(tmp_path, pins, download=True)
    assert list(tmp_path.iterdir()) == []


def test_cli_verifies_the_exact_generated_appimage(tmp_path, monkeypatch):
    root = tmp_path / 'checkout'
    bundle = root / 'dist/MediaWrapper'
    bundle.mkdir(parents=True)
    (bundle / 'build-info.json').write_text(json.dumps({'commit': 'abcdef0123456789', 'source_dirty': True}))
    (bundle / 'SHA256SUMS.json').write_text('{}')
    (bundle / 'MediaWrapper').write_text('payload')
    (root / 'pyproject.toml').write_text('[project]\nversion = "1.2.3"\n')
    (root / 'src/media_wrapper/resources').mkdir(parents=True)
    (root / 'src/media_wrapper/resources/icon.svg').write_text('<svg/>')
    (root / 'packaging').mkdir()
    tool = tmp_path / 'tools/appimagetool'
    tool.parent.mkdir()
    tool.write_bytes(b'pinned tool')
    pins = {'tool': {'name': tool.name, 'sha256': module.digest(tool), 'url': 'https://example.invalid/tool'},
            'runtime': {'name': tool.name, 'sha256': module.digest(tool), 'url': 'https://example.invalid/tool'}}
    (root / 'packaging/appimage-tools.json').write_text(json.dumps(pins))
    monkeypatch.setattr(module, 'ROOT', root)
    monkeypatch.setattr(module.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(module.platform, 'platform', lambda: 'Linux-x86_64-test')
    monkeypatch.setattr(module.sys, 'argv', ['build_appimage.py', '--tools', str(tool.parent), '--verify'])
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[0] == str(tool):
            Path(command[-1]).write_bytes(b'AppImage')

    monkeypatch.setattr(module.subprocess, 'run', run)
    module.main()
    output = root / 'dist/MediaWrapper-1.2.3-Linux-x86_64-abcdef012345-dirty.AppImage'
    assert output.read_bytes() == b'AppImage'
    assert output.with_name(output.name + '.sha256').read_text() == f'{module.digest(output)}  {output.name}\n'
    assert calls[-1] == [module.sys.executable, str(root / 'scripts/verify_distribution.py'),
                         str(bundle), '--appimage', str(output)]
    assert not list((root / 'build').iterdir())
