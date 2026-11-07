"""Environment, inventory and orchestration failures must stop release packaging."""
import json
import os
import subprocess
from types import SimpleNamespace

import build_distribution
import build_release
import pytest
import verify_linux_compatibility as elf
from distribution_common import sha256, verify_manifest


def payload(directory, *, target='Linux'):
    directory.mkdir(parents=True)
    (directory / ('MediaWrapper.exe' if target == 'Windows' else 'MediaWrapper')).write_bytes(b'\x7fELFfixture')
    (directory / 'build-info.json').write_text(json.dumps({
        'commit': 'a' * 40, 'source_dirty': False, 'target_os': target, 'machine': 'AMD64'}))
    (directory / 'SHA256SUMS.json').write_text(json.dumps({
        path.name: sha256(path) for path in directory.iterdir()}))
    return directory


def test_inventory_rejects_extra_missing_changed_and_escaping_files(tmp_path):
    bundle = payload(tmp_path / 'payload')
    verify_manifest(bundle)
    extra = bundle / 'extra.dll'
    extra.touch()
    with pytest.raises(ValueError, match='unexpected'):
        verify_manifest(bundle)
    extra.unlink()
    executable = bundle / 'MediaWrapper'
    original = executable.read_bytes()
    executable.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='checksum'):
        verify_manifest(bundle)
    executable.unlink()
    with pytest.raises(ValueError, match='missing'):
        verify_manifest(bundle)
    outside = tmp_path / 'outside'
    outside.write_bytes(original)
    try:
        executable.symlink_to(outside)
    except OSError:
        pytest.skip('Symlink creation is unavailable for this Windows account')
    with pytest.raises(ValueError, match='Unsafe'):
        verify_manifest(bundle)


@pytest.mark.parametrize(('python', 'machine', 'libc', 'message'), [
    ((3, 14), 'x86_64', ('glibc', '2.31'), 'Python 3.11'),
    ((3, 11), 'aarch64', ('glibc', '2.31'), 'x86-64'),
    ((3, 11), 'x86_64', ('glibc', '2.35'), 'Debian 11'),
    ((3, 11), 'x86_64', ('musl', '1.2'), 'Debian 11'),
])
def test_environment_rejected_before_loading_qt(monkeypatch, python, machine, libc, message):
    monkeypatch.setattr(build_distribution.sys, 'platform', 'linux')
    monkeypatch.setattr(build_distribution.sys, 'version_info', python)
    monkeypatch.setattr(build_distribution.platform, 'machine', lambda: machine)
    monkeypatch.setattr(build_distribution.platform, 'libc_ver', lambda: libc)
    with pytest.raises(SystemExit, match=message):
        build_distribution.check_environment()


def test_wrong_qt_pin_is_rejected(monkeypatch):
    monkeypatch.setattr(build_distribution.sys, 'platform', 'linux')
    monkeypatch.setattr(build_distribution.sys, 'version_info', (3, 11))
    monkeypatch.setattr(build_distribution.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(build_distribution.platform, 'libc_ver', lambda: ('glibc', '2.31'))
    monkeypatch.setattr(build_distribution.importlib.metadata, 'version', lambda _: '6.12.0')
    with pytest.raises(SystemExit, match='PySide6 6.12.0'):
        build_distribution.check_environment()


def test_qt_license_texts_include_verifiable_provenance_and_reject_tampering(tmp_path, monkeypatch):
    target = tmp_path / 'licenses'
    build_distribution.copy_qt_license_texts(target)
    inventory = json.loads((target / 'SOURCES.json').read_text())
    assert 'Debian 11' in inventory['source']
    assert set(inventory['files_sha256']) == {'GPL-2.txt', 'GPL-3.txt', 'LGPL-3.txt'}
    assert all(sha256(target / name) == expected for name, expected in inventory['files_sha256'].items())
    (target / 'LGPL-3.txt').write_text('tampered')
    # Reuse the copied directory as an input fixture, without changing repository licenses.
    fake_root = tmp_path / 'fake'
    (fake_root / 'packaging').mkdir(parents=True)
    import shutil
    shutil.copytree(target, fake_root / 'packaging/licenses')
    monkeypatch.setattr(build_distribution, 'ROOT', fake_root)
    with pytest.raises(ValueError, match='license checksum mismatch'):
        build_distribution.copy_qt_license_texts(tmp_path / 'bad-output')


def test_glibc_audit_only_uses_requirements_and_rejects_newer_libc(tmp_path, monkeypatch):
    output = 'Version definition section:\nName: GLIBC_2.99\nVersion needs section:\nName: GLIBC_2.28\nName: GLIBC_2.31'
    assert elf.required_glibc(output) == [(2, 28), (2, 31)]
    with pytest.raises(ValueError, match='Unsupported glibc'):
        elf.required_glibc('Version needs section:\nName: GLIBC_ABI_DT_RELR')
    bundle = payload(tmp_path / 'payload')
    monkeypatch.setattr(elf.sys, 'platform', 'linux')
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, 'Version needs section:\nName: GLIBC_2.32', '')
    monkeypatch.setattr(elf.subprocess, 'run', run)
    with pytest.raises(ValueError, match='requires glibc 2.32'):
        elf.verify(bundle)


def test_glibc_audit_rejects_missing_dynamic_libraries(tmp_path, monkeypatch):
    bundle = payload(tmp_path / 'payload')
    monkeypatch.setattr(elf.sys, 'platform', 'linux')
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0,
            'Version needs section:\nName: GLIBC_2.28' if args[0] == 'readelf' else 'libmissing.so => not found', '')
    monkeypatch.setattr(elf.subprocess, 'run', run)
    with pytest.raises(ValueError, match='Unresolved runtime'):
        elf.verify(bundle)


def test_glibc_audit_uses_the_frozen_loader_path_for_bundled_dependencies(tmp_path, monkeypatch):
    bundle = payload(tmp_path / 'payload')
    monkeypatch.setattr(elf.sys, 'platform', 'linux')
    monkeypatch.setenv('LD_LIBRARY_PATH', '/original')
    environments = []
    def run(args, **kwargs):
        environments.append(kwargs['env']['LD_LIBRARY_PATH'])
        return subprocess.CompletedProcess(args, 0,
            'Version needs section:\nName: GLIBC_2.28' if args[0] == 'readelf' else 'libffi.so.7 => bundled', '')
    monkeypatch.setattr(elf.subprocess, 'run', run)
    report = elf.verify(bundle)
    assert report['success'] and report['elf_count'] == 1
    assert environments and all(value == str(bundle / '_internal') + os.pathsep + '/original' for value in environments)


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    root = tmp_path / 'checkout with spaces'
    root.mkdir()
    (root / 'pyproject.toml').write_text('[project]\nversion = "0.1.0"\n')
    output = tmp_path / 'release ü'
    monkeypatch.setattr(build_release, 'ROOT', root)
    monkeypatch.setattr(build_release, 'check_environment', dict)
    monkeypatch.setattr(build_release.sys, 'platform', 'linux')
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if any(str(arg).endswith('build_distribution.py') for arg in args):
            payload(output / 'MediaWrapper')
        if any(str(arg).endswith('build_appimage.py') for arg in args) and '--tools-only' not in args:
            (output / ('MediaWrapper-0.1.0-Linux-x86_64-' + 'a' * 12 + '.AppImage')).write_bytes(b'image')
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(build_release.subprocess, 'run', run)
    return SimpleNamespace(output=output, calls=calls)


def test_release_uses_selected_output_and_records_all_required_checks(pipeline):
    manifest = pipeline.output.parent / 'explicit-tools.json'
    report_path = build_release.run_release(pipeline.output, offline_tools=True, tools_manifest=manifest)
    report = json.loads(report_path.read_text())
    assert report['success'] and not report['tests_skipped']
    assert {item['name'] for item in report['stages']} >= {
        'tests', 'lint', 'elf-verify', 'portable-verify', 'appimage-verify',
        'desktop-verify', 'archive', 'archive-verify'}
    build = next(args for args in pipeline.calls if any(str(arg).endswith('build_distribution.py') for arg in args))
    assert build[-2:] == ['--output-dir', str(pipeline.output)]
    assert not any('--download-tools' in args for args in pipeline.calls)
    for args in pipeline.calls:
        if any(str(arg).endswith('build_appimage.py') for arg in args):
            assert '--tools-manifest' in args and str(manifest) in args
    before = (pipeline.output / 'MediaWrapper/MediaWrapper').read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        build_release.run_release(pipeline.output)
    assert (pipeline.output / 'MediaWrapper/MediaWrapper').read_bytes() == before


def test_failed_stage_saves_log_and_never_starts_packaging(pipeline, monkeypatch):
    def fail(args, **kwargs):
        kwargs['stdout'].write('failure detail')
        return subprocess.CompletedProcess(args, 37)
    monkeypatch.setattr(build_release.subprocess, 'run', fail)
    with pytest.raises(RuntimeError, match='dependencies failed'):
        build_release.run_release(pipeline.output)
    report_path, = pipeline.output.glob('reports/*/build-status.json')
    report = json.loads(report_path.read_text())
    assert not report['success'] and report['stages'][0]['returncode'] == 37
    assert (report_path.parent / 'dependencies.log').read_text() == 'failure detail'
    assert not (pipeline.output / 'MediaWrapper').exists()
