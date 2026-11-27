"""Native per-user install, real processing, reinstall and safe uninstall verification."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from distribution_common import sha256


def ensure_no_existing_installation():
    import winreg

    recipe = Path(__file__).resolve().parents[1] / 'packaging/MediaWrapper.iss'
    app_id = next(line.removeprefix('AppId=') for line in recipe.read_text(encoding='utf-8').splitlines()
                  if line.startswith('AppId=')).removeprefix('{')
    key = f'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{app_id}_is1'
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view):
                    raise RuntimeError('MediaWrapper is already registered. Verify the installer in a fresh Windows account or VM.')
            except FileNotFoundError:
                continue


def run_installer(installer, directory):
    result = subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                             f'/DIR={directory}'], capture_output=True, encoding='utf-8', errors='replace',
                            timeout=120, check=False)
    if result.returncode:
        raise RuntimeError(f'Installer failed ({result.returncode}): {result.stdout}\n{result.stderr}')


def run_uninstaller(uninstaller):
    result = subprocess.run([str(uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
                            capture_output=True, encoding='utf-8', errors='replace', timeout=120, check=False)
    if result.returncode:
        raise RuntimeError(f'Uninstaller failed ({result.returncode}): {result.stdout}\n{result.stderr}')


def check_preserved(snapshots):
    for path, digest in snapshots.items():
        if not path.is_file() or sha256(path) != digest:
            raise RuntimeError(f'Installer lifecycle changed user data: {path}')


def verify(installer):
    if sys.platform != 'win32':
        raise RuntimeError('Installer verification requires native Windows')
    ensure_no_existing_installation()
    with tempfile.TemporaryDirectory(prefix='Media Wrapper ü installer ') as temporary:
        root = Path(temporary)
        installation = root / 'installed app'
        executable = installation / 'MediaWrapper.exe'
        uninstaller = installation / 'unins000.exe'
        try:
            run_installer(installer, installation)
            return verify_lifecycle(installer, root, installation, executable, uninstaller)
        finally:
            if executable.is_file() and uninstaller.is_file():
                try:
                    run_uninstaller(uninstaller)
                except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                    print(f'Could not clean up the temporary installation: {error}', file=sys.stderr)


def verify_lifecycle(installer, root, installation, executable, uninstaller):
    if not executable.is_file() or not uninstaller.is_file():
        raise RuntimeError('Installer did not create the expected application and uninstaller')
    source = root / 'source ü клип with spaces.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=96x64:r=12:d=0.5',
                    '-f', 'lavfi', '-i', 'sine=duration=0.5', '-c:v', 'ffv1', '-c:a', 'pcm_s16le', '-n', str(source)],
                   check=True, capture_output=True, timeout=30)
    source_digest = sha256(source)
    output = root / 'user outputs'
    output.mkdir()
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    for name in ('PYTHONPATH', 'QT_PLUGIN_PATH'):
        environment.pop(name, None)
    result = subprocess.run([str(executable), '--verify-install', str(source), str(output)],
                            env=environment, cwd=root, capture_output=True, encoding='utf-8', errors='replace',
                            timeout=120, check=False)
    report_file = output / 'verification.json'
    if result.returncode:
        report_message = report_file.read_text(encoding='utf-8') if report_file.is_file() else 'No report'
        raise RuntimeError(f'Installed application failed ({result.returncode}): '
                           f'{result.stdout}\n{result.stderr}\n{report_message}')
    report = json.loads(report_file.read_text(encoding='utf-8'))
    if (not all(report.get(key) for key in ('success', 'outputs_verified', 'history_persisted', 'immutable_snapshots'))
            or report.get('tasks') != ['Completed'] * 3 or report.get('player_instantiated') is not False):
        raise RuntimeError(f'Installed application verification did not pass: {report}')
    queue = output / 'data/queue.sqlite3'
    with queue.open('rb') as database:
        if database.read(16) != b'SQLite format 3\x00':
            raise RuntimeError('Packaged application did not create an SQLite queue')
    # The installer does not own this file even though it is in the application directory.
    user_file = installation / 'user-media-keep.mkv'
    user_file.write_bytes(b'user-owned media')
    snapshots = {path: sha256(path) for path in (
        output / 'config/settings.json', queue, output / 'remux.mkv', output / 'convert.mp4',
        output / 'compress.mp4', user_file,
    )}
    snapshots[source] = source_digest
    check_preserved(snapshots)
    run_installer(installer, installation)
    check_preserved(snapshots)
    if not executable.is_file():
        raise RuntimeError('Application is missing after reinstall')
    run_uninstaller(uninstaller)
    if executable.exists():
        raise RuntimeError('Uninstall did not remove the application executable')
    check_preserved(snapshots)
    result_report = {'installer': 'passed', 'reinstall': 'passed', 'uninstall': 'passed',
                     'user_data_preserved': True, **report}
    print(json.dumps(result_report))
    return result_report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('installer', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = verify(args.installer.resolve())
    if args.report:
        with args.report.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
