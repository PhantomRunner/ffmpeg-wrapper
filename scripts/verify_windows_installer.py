"""Native per-user install, real processing, upgrade and safe uninstall verification."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run_installer(installer, directory):
    result = subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                             f'/DIR={directory}'], capture_output=True, text=True, timeout=120, check=False)
    if result.returncode:
        raise RuntimeError(f'Installer failed ({result.returncode}): {result.stdout}\n{result.stderr}')


def verify(installer):
    if sys.platform != 'win32':
        raise RuntimeError('Installer verification requires native Windows')
    with tempfile.TemporaryDirectory(prefix='Media Wrapper ü installer ') as temporary:
        root = Path(temporary)
        installation = root / 'installed app'
        run_installer(installer, installation)
        executable = installation / 'MediaWrapper.exe'
        assert executable.is_file()
        source = root / 'source ü with spaces.mkv'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=96x64:r=12:d=0.5',
                        '-f', 'lavfi', '-i', 'sine=duration=0.5', '-c:v', 'ffv1', '-c:a', 'pcm_s16le', '-n', str(source)],
                       check=True, capture_output=True, timeout=30)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        output = root / 'user outputs'
        output.mkdir()
        result = subprocess.run([str(executable), '--verify-install', str(source), str(output)],
                                env=dict(os.environ, QT_QPA_PLATFORM='offscreen'), cwd=root,
                                capture_output=True, text=True, timeout=120, check=False)
        if result.returncode:
            raise RuntimeError(f'Installed application failed: {result.stdout}\n{result.stderr}')
        report = json.loads((output / 'verification.json').read_text())
        assert report['success'] and report['outputs_verified'] and report['history_persisted'], report
        assert report['immutable_snapshots'] and report['player_instantiated'] is False, report
        settings = (output / 'config/settings.json').read_bytes()
        history = (output / 'data/history.json').read_bytes()
        # An untracked user file inside the app folder is deliberately preserved.
        user_file = installation / 'user-media-keep.mkv'
        user_file.write_bytes(b'user-owned media')
        run_installer(installer, installation)
        assert user_file.read_bytes() == b'user-owned media'
        assert (output / 'config/settings.json').read_bytes() == settings
        uninstaller = installation / 'unins000.exe'
        subprocess.run([str(uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
                       check=True, capture_output=True, timeout=120)
        assert not executable.exists() and user_file.read_bytes() == b'user-owned media'
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        assert (output / 'config/settings.json').read_bytes() == settings
        assert (output / 'data/history.json').read_bytes() == history
        assert (output / 'convert.mp4').is_file() and (output / 'compress.mp4').is_file()
        print(json.dumps({'installer': 'passed', 'upgrade': 'passed', 'uninstall': 'passed',
                          'user_data_preserved': True, **report}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('installer', type=Path)
    verify(parser.parse_args().installer.resolve())
