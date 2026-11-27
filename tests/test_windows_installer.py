import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from media_wrapper.domain.tasks import TaskStatus
from media_wrapper.infrastructure.installation_guard import MUTEX_NAME

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('windows_installer_builder', ROOT / 'scripts/build_windows_installer.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

spec = importlib.util.spec_from_file_location('windows_installer_verifier', ROOT / 'scripts/verify_windows_installer.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def test_native_payload_checksums_are_checked_before_compiling(tmp_path):
    bundle = tmp_path / 'Windows payload with spaces'
    bundle.mkdir()
    executable = bundle / 'MediaWrapper.exe'
    executable.write_bytes(b'test payload')
    manifest = {'MediaWrapper.exe': hashlib.sha256(executable.read_bytes()).hexdigest()}
    info = {'platform': 'Windows-11', 'ffmpeg_bundled': False}
    (bundle / 'build-info.json').write_text(json.dumps(info))
    manifest['build-info.json'] = hashlib.sha256((bundle / 'build-info.json').read_bytes()).hexdigest()
    (bundle / 'SHA256SUMS.json').write_text(json.dumps(manifest))
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


def test_pinned_compiler_is_installed_portably_for_current_user(tmp_path, monkeypatch):
    installer = tmp_path / 'compiler setup.exe'
    installer.write_bytes(b'compiler distribution')
    pin = {'name': installer.name, 'sha256': hashlib.sha256(installer.read_bytes()).hexdigest()}
    compiler = tmp_path / 'compiler/ISCC.exe'
    calls = []

    def install(args, **kwargs):
        calls.append(args)
        compiler.parent.mkdir()
        compiler.touch()

    monkeypatch.setattr(builder.subprocess, 'run', install)
    assert builder.prepare_compiler(tmp_path, pin, download=False) == compiler
    assert builder.prepare_compiler(tmp_path, pin, download=False) == compiler
    assert len(calls) == 1
    assert {'/PORTABLE=1', '/CURRENTUSER', f'/DIR={compiler.parent.resolve()}'}.issubset(calls[0])


def test_installer_refuses_registered_profile(monkeypatch):
    from contextlib import nullcontext

    registry = SimpleNamespace(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2, KEY_READ=1, KEY_WOW64_64KEY=2, KEY_WOW64_32KEY=4,
                               OpenKey=lambda *args: nullcontext())
    monkeypatch.setitem(sys.modules, 'winreg', registry)
    with pytest.raises(RuntimeError, match='already registered'):
        verifier.ensure_no_existing_installation()


@pytest.mark.parametrize('tamper_during', (None, 'reinstall', 'uninstall'))
def test_installer_lifecycle_checks_real_queue_database(tmp_path, monkeypatch, tamper_during):
    monkeypatch.setattr(verifier, 'sys', SimpleNamespace(platform='win32', stderr=sys.stderr))
    monkeypatch.setattr(verifier, 'ensure_no_existing_installation', lambda: None)
    installer = tmp_path / 'setup.exe'
    installed = []
    databases = []
    uninstalled = []

    def fake_install(package, directory):
        assert package == installer
        directory.mkdir(exist_ok=True)
        for name in ('MediaWrapper.exe', 'unins000.exe'):
            (directory / name).touch()
        if installed and tamper_during == 'reinstall':
            databases[0].write_bytes(b'damaged during reinstall')
        installed.append(directory)

    def fake_run(args, **kwargs):
        if args[0] == 'ffmpeg':
            Path(args[-1]).write_bytes(b'fixture')
        else:
            assert args[1] == '--verify-install'
            assert 'PYTHONPATH' not in kwargs['env']
            folder = Path(args[3])
            (folder / 'config').mkdir()
            (folder / 'config/settings.json').write_text('{}', encoding='utf-8')
            (folder / 'data').mkdir()
            database = folder / 'data/queue.sqlite3'
            connection = sqlite3.connect(database)
            try:
                connection.execute('create table sample (job_id integer)')
                connection.execute('insert into sample values (1)')
                connection.commit()
            finally:
                connection.close()
            databases.append(database)
            for name in ('remux.mkv', 'convert.mp4', 'compress.mp4'):
                (folder / name).write_bytes(b'processed fixture')
            report = {'success': True, 'outputs_verified': True, 'history_persisted': True, 'immutable_snapshots': True,
                      'player_instantiated': False, 'tasks': [TaskStatus.COMPLETED.value] * 3}
            (folder / 'verification.json').write_text(json.dumps(report), encoding='utf-8')
        return subprocess.CompletedProcess(args, 0)

    def fake_uninstall(uninstaller):
        uninstaller.unlink()
        uninstaller.with_name('MediaWrapper.exe').unlink()
        if tamper_during == 'uninstall':
            databases[0].write_bytes(b'damaged during uninstall')
        uninstalled.append(uninstaller)

    monkeypatch.setattr(verifier, 'run_installer', fake_install)
    monkeypatch.setattr(verifier, 'run_uninstaller', fake_uninstall)
    monkeypatch.setattr(verifier, 'subprocess', SimpleNamespace(run=fake_run, SubprocessError=subprocess.SubprocessError))
    if tamper_during:
        with pytest.raises(RuntimeError, match='changed user data: .*queue.sqlite3'):
            verifier.verify(installer)
    else:
        assert verifier.verify(installer)['user_data_preserved']
    assert len(installed) == 2 and len(uninstalled) == 1


@pytest.mark.skipif(sys.platform != 'win32' or sys.version_info[:2] != (3, 11), reason='Native Windows x64 Python 3.11 launcher')
def test_windows_build_launcher_uses_fresh_outputs_and_explicitly_skips_installer(tmp_path):
    checkout = tmp_path / 'checkout with ü and Ю'
    scripts = checkout / 'scripts'
    scripts.mkdir(parents=True)
    shutil.copy(ROOT / 'build.cmd', checkout)
    shutil.copy(ROOT / 'scripts/build_windows.ps1', scripts)
    # Exercise the actual Windows scripts without downloading dependencies or building the payload twice.
    (checkout / 'pip.py').touch()
    (scripts / 'build_release.py').write_text(
        'import json, sys\nfrom pathlib import Path\n'
        'output = Path(sys.argv[sys.argv.index("--output-dir") + 1])\n'
        '(output / "invocation.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")\n',
        encoding='utf-8',
    )
    tools = tmp_path / 'tools with spaces'
    tools.mkdir()
    for tool in ('git', 'ffmpeg', 'ffprobe'):
        (tools / f'{tool}.cmd').write_text('@exit /b 0\n', encoding='ascii')
    environment = dict(os.environ, PATH=str(tools), PATHEXT='.COM;.EXE;.BAT;.CMD')
    system = Path(os.environ['SystemRoot']) / 'System32'

    def launch(args, success=True):
        result = subprocess.run(args, cwd=checkout, env=environment, capture_output=True, encoding='utf-8',
                                errors='replace', timeout=60, check=False)
        assert (result.returncode == 0) == success, result.stdout + result.stderr
        return result

    local = [str(system / 'cmd.exe'), '/d', '/c', 'build.cmd', '-Python', sys.executable]
    launch(local)
    launch(local)
    outputs = list((checkout / 'dist/builds/windows-x86_64').glob('*/invocation.json'))
    assert len(outputs) == 2
    for invocation in outputs:
        assert json.loads(invocation.read_text(encoding='utf-8')) == [
            '--output-dir', str(invocation.parent), '--skip-installer-verification',
        ]

    destination = tmp_path / 'release output ü'
    powershell = system / 'WindowsPowerShell/v1.0/powershell.exe'
    launch([str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
            str(scripts / 'build_windows.ps1'), '-Python', sys.executable, '-OutputDir', str(destination),
            '-OfflineTools', '-SkipTests'])
    assert json.loads((destination / 'invocation.json').read_text(encoding='utf-8')) == [
        '--output-dir', str(destination), '--offline-tools', '--skip-tests',
    ]

    (tools / 'ffmpeg.cmd').unlink()
    result = launch(local, success=False)
    assert 'ffmpeg is required' in result.stderr
    assert len(list((checkout / 'dist/builds/windows-x86_64').iterdir())) == 2
