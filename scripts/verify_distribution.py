"""Copy, exercise and remove only a temporary installation owned by this check."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from distribution_common import verify_manifest


def verify(bundle: Path, appimage: Path | None = None, *, archive: Path | None = None,
           qt_platform: str = 'offscreen') -> dict:
    verify_manifest(bundle)
    with tempfile.TemporaryDirectory(prefix='Media Wrapper ü installation ') as temporary:
        root = Path(temporary)
        install = root / 'portable app'
        if archive:
            shutil.unpack_archive(archive, root / 'archive')
            shutil.move(str(root / 'archive/MediaWrapper'), install)
            verify_manifest(install)
        else:
            shutil.copytree(bundle, install, symlinks=True)
        executable = install / ('MediaWrapper.exe' if os.name == 'nt' else 'MediaWrapper')
        if appimage is not None:
            executable = install / 'MediaWrapper.AppImage'
            shutil.copy2(appimage, executable)
            executable.chmod(0o755)
        source_directory = root / 'read only source' / ('long-path-' + 'x' * 180)
        source_directory.mkdir(parents=True)
        source = source_directory / 'clip ü клип with spaces.mkv'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=96x64:r=12:d=0.5',
                        '-f', 'lavfi', '-i', 'sine=duration=0.5', '-c:v', 'ffv1', '-c:a', 'pcm_s16le', '-n', str(source)],
                       check=True, capture_output=True, timeout=30)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        output = root / 'new outputs'
        output.mkdir()
        environment = dict(os.environ, QT_QPA_PLATFORM=qt_platform)
        if appimage is not None:
            environment['APPIMAGE_EXTRACT_AND_RUN'] = '1'
        environment.pop('PYTHONPATH', None)
        environment.pop('QT_PLUGIN_PATH', None)
        try:
            if os.name != 'nt':
                source.chmod(0o444)
                source_directory.chmod(0o555)
            result = subprocess.run([str(executable), '--verify-install', str(source), str(output)],
                                    env=environment, cwd=root, capture_output=True, text=True, timeout=120, check=False)
            if result.returncode:
                raise RuntimeError(f'Packaged check failed ({result.returncode}): {result.stdout}\n{result.stderr}\n'
                                   + ((output / 'verification.json').read_text() if (output / 'verification.json').exists() else 'No report'))
            report = json.loads((output / 'verification.json').read_text())
            assert report['success'] and len(report['tasks']) == 3, report
            assert report['outputs_verified'] and report['immutable_snapshots'] and report['history_persisted'], report
            assert report['player_instantiated'] is False, report
            assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
            assert (output / 'config/settings.json').is_file()
            # A fresh normal application must open even when processing helpers are absent.
            empty_path = root / 'no ffmpeg here'
            empty_path.mkdir()
            startup_environment = dict(environment, PATH=str(empty_path),
                                       XDG_CONFIG_HOME=str(root / 'smoke-config'),
                                       XDG_DATA_HOME=str(root / 'smoke-data'),
                                       APPDATA=str(root / 'smoke-roaming'), LOCALAPPDATA=str(root / 'smoke-local'))
            startup = subprocess.run([str(executable), '--smoke-test'], env=startup_environment,
                                     cwd=root, capture_output=True, text=True, timeout=30, check=False)
            if startup.returncode != 2:
                raise RuntimeError(f'Expected missing-FFmpeg startup status 2, got {startup.returncode}: '
                                   f'{startup.stdout}\n{startup.stderr}')
            shutil.rmtree(install)
            assert not install.exists() and source.exists() and (output / 'convert.mp4').exists()
            result_report = {'installation': 'passed', 'removal': 'passed', 'source_unchanged': True,
                             'missing_ffmpeg_startup': 'passed', 'qt_platform': qt_platform,
                             'archive': archive.name if archive else None, **report}
            print(json.dumps(result_report))
            return result_report
        finally:
            if os.name != 'nt':
                source_directory.chmod(0o755)
                source.chmod(0o644)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--appimage', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--platform', choices=('offscreen', 'xcb'), default='offscreen')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = verify(args.bundle.resolve(), args.appimage.resolve() if args.appimage else None,
                    archive=args.archive.resolve() if args.archive else None, qt_platform=args.platform)
    if args.report:
        with args.report.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
