"""Exercise an existing release in a clean Linux userspace (Python 3.9+ controller)."""
import argparse
import json
import os
import subprocess
import uuid
from pathlib import Path


def verify(output: Path) -> dict:
    images = list(output.glob('MediaWrapper-*.AppImage'))
    archives = list(output.glob('MediaWrapper-*.tar.gz'))
    if len(images) != 1 or len(archives) != 1:
        raise ValueError('Choose the output directory of one complete Linux build (one AppImage and tar.gz)')
    reports = output / 'reports' / ('runtime-' + uuid.uuid4().hex[:12])
    reports.mkdir(parents=True)
    status = {'success': False, 'os_release': Path('/etc/os-release').read_text(), 'stages': []}
    scripts = Path(__file__).resolve().parent
    bundle = output / 'MediaWrapper'
    commands = [
        ('elf', ['python3', str(scripts / 'verify_linux_compatibility.py'), str(bundle),
                 '--appimage', str(images[0]), '--report', str(reports / 'elf.json')]),
        ('portable', ['python3', str(scripts / 'verify_distribution.py'), str(bundle)]),
        ('appimage', ['python3', str(scripts / 'verify_distribution.py'), str(bundle), '--appimage', str(images[0])]),
        ('portable-xcb', ['xvfb-run', '-a', 'python3', str(scripts / 'verify_distribution.py'), str(bundle), '--platform', 'xcb']),
        ('appimage-xcb', ['xvfb-run', '-a', 'python3', str(scripts / 'verify_distribution.py'), str(bundle),
                          '--platform', 'xcb', '--appimage', str(images[0])]),
        ('archive', ['python3', str(scripts / 'verify_distribution.py'), str(bundle), '--archive', str(archives[0])]),
    ]
    try:
        for name, command in commands:
            if name != 'elf':
                command += ['--report', str(reports / (name + '.json'))]
            print(f'[{name}] {reports}', flush=True)
            with (reports / (name + '.log')).open('x', encoding='utf-8') as log:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                        env=dict(os.environ, QT_QPA_PLATFORM='offscreen'), check=False)
            status['stages'].append({'name': name, 'returncode': result.returncode})
            if result.returncode:
                raise RuntimeError((reports / (name + '.log')).read_text(encoding='utf-8', errors='replace')[-8000:])
        status['success'] = True
    except BaseException as error:
        status['error'] = str(error)
        raise
    finally:
        (reports / 'runtime-status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    print(f'Clean-runtime checks passed: {reports}', flush=True)
    return status


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', type=Path)
    verify(parser.parse_args().output_dir.resolve())
