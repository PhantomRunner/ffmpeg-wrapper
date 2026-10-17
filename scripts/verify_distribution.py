"""Copy, exercise and remove only a temporary installation owned by this check."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def verify(bundle: Path) -> None:
    manifest = json.loads((bundle / 'SHA256SUMS.json').read_text(encoding='utf-8'))
    for name, expected in manifest.items():
        if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Build checksum mismatch: {name}')
    with tempfile.TemporaryDirectory(prefix='Media Wrapper ü installation ') as temporary:
        root = Path(temporary)
        install = root / 'portable app'
        shutil.copytree(bundle, install, symlinks=True)
        executable = install / ('MediaWrapper.exe' if os.name == 'nt' else 'MediaWrapper')
        source_directory = root / 'read only source' / ('long-path-' + 'x' * 180)
        source_directory.mkdir(parents=True)
        source = source_directory / 'clip ü with spaces.mkv'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=96x64:r=12:d=0.5',
                        '-f', 'lavfi', '-i', 'sine=duration=0.5', '-c:v', 'ffv1', '-c:a', 'pcm_s16le', '-n', str(source)],
                       check=True, capture_output=True, timeout=30)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        output = root / 'new outputs'
        output.mkdir()
        environment = dict(os.environ, QT_QPA_PLATFORM='offscreen')
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
            assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
            assert (output / 'config/settings.json').is_file()
            shutil.rmtree(install)
            assert not install.exists() and source.exists() and (output / 'convert.mp4').exists()
            print(json.dumps({'installation': 'passed', 'removal': 'passed', 'source_unchanged': True, **report}))
        finally:
            if os.name != 'nt':
                source_directory.chmod(0o755)
                source.chmod(0o644)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('bundle', type=Path)
    verify(parser.parse_args().bundle.resolve())
