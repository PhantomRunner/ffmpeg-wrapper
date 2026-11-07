"""Build, test and package one native distribution, recording every stage."""
import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from build_distribution import check_environment
from distribution_common import artifact_name, sha256, verify_manifest

ROOT = Path(__file__).resolve().parents[1]


def run_release(output_dir: Path, *, reuse_bundle: bool = False,
                skip_tests: bool = False, offline_tools: bool = False,
                tools_manifest: Path | None = None) -> Path:
    output_dir = output_dir.resolve()
    bundle = output_dir / 'MediaWrapper'
    if bundle.exists() and not reuse_bundle:
        raise ValueError(f'{bundle} already exists; choose --output-dir or explicitly --reuse-bundle')
    if reuse_bundle and not bundle.is_dir():
        raise ValueError('--reuse-bundle requires an existing MediaWrapper directory')
    check_environment()
    run_id = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    reports = output_dir / 'reports' / run_id
    reports.mkdir(parents=True)
    status = {'success': False, 'platform': sys.platform, 'output_dir': str(output_dir),
              'started_utc': run_id, 'tests_skipped': skip_tests, 'stages': []}
    status_path = reports / 'build-status.json'

    def save():
        status_path.write_text(json.dumps(status, indent=2), encoding='utf-8')

    def step(name, arguments, *, environment=None):
        entry = {'name': name, 'command': arguments, 'status': 'running', 'log': name + '.log'}
        status['stages'].append(entry)
        save()
        print(f'[{name}] {reports / entry["log"]}', flush=True)
        with (reports / entry['log']).open('x', encoding='utf-8') as log:
            result = subprocess.run(arguments, cwd=ROOT, env=environment, stdout=log,
                                    stderr=subprocess.STDOUT, check=False, timeout=600)
        entry.update(status='passed' if result.returncode == 0 else 'failed', returncode=result.returncode)
        save()
        if result.returncode:
            print((reports / entry['log']).read_text(encoding='utf-8', errors='replace')[-8000:], file=sys.stderr)
            raise RuntimeError(f'{name} failed ({result.returncode}); see {reports}')

    def python(script, *arguments):
        return [sys.executable, str(ROOT / 'scripts' / script), *map(str, arguments)]

    try:
        step('dependencies', [sys.executable, '-m', 'pip', 'check'])
        # Integration tests must not silently skip because FFmpeg is missing.
        step('ffmpeg', ['ffmpeg', '-version'])
        step('ffprobe', ['ffprobe', '-version'])
        if not skip_tests:
            step('lint', [sys.executable, '-m', 'ruff', 'check', '--no-cache', '.'])
            step('tests', [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'],
                 environment=dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1',
                                  PYTHONFAULTHANDLER='1'))
        if sys.platform == 'linux':
            tools_arguments = [] if offline_tools else ['--download-tools']
            manifest_arguments = ['--tools-manifest', str(tools_manifest)] if tools_manifest else []
            step('appimage-tools', python('build_appimage.py', '--tools-only', *tools_arguments, *manifest_arguments))
        if not reuse_bundle:
            step('portable-build', python('build_distribution.py', '--output-dir', output_dir))
        verify_manifest(bundle)
        info = json.loads((bundle / 'build-info.json').read_text(encoding='utf-8'))
        expected_os = 'Windows' if sys.platform == 'win32' else 'Linux'
        if info.get('target_os', info.get('platform', '').split('-')[0]) != expected_os:
            raise ValueError('Portable payload belongs to a different operating system')
        name = artifact_name(ROOT, info)
        step('portable-verify', python('verify_distribution.py', bundle, '--report', reports / 'portable.json'))
        if sys.platform == 'linux':
            step('elf-verify', python('verify_linux_compatibility.py', bundle, '--report', reports / 'elf.json'))
            step('appimage-build', python('build_appimage.py', '--output-dir', output_dir, *manifest_arguments))
            image = output_dir / (name + '.AppImage')
            step('appimage-verify', python('verify_distribution.py', bundle, '--appimage', image,
                                           '--report', reports / 'appimage.json'))
            step('appimage-elf-verify', python('verify_linux_compatibility.py', bundle, '--appimage', image,
                                               '--report', reports / 'appimage-elf.json'))
            step('desktop-verify', ['xvfb-run', '-a', *python('verify_distribution.py', bundle,
                  '--appimage', image, '--platform', 'xcb', '--report', reports / 'desktop.json')])
        else:
            compiler = ROOT / 'build/inno-tools/compiler/ISCC.exe'
            step('installer-compiler', python('build_windows_installer.py', '--prepare-compiler',
                                              *(['--offline'] if offline_tools else [])))
            step('installer-build', python('build_windows_installer.py', '--bundle', bundle,
                                           '--output-dir', output_dir, '--compiler', compiler))
            step('installer-verify', python('verify_windows_installer.py', output_dir / (name + '-setup.exe'),
                                            '--report', reports / 'installer.json'))
        step('archive', python('archive_distribution.py', '--output-dir', output_dir))
        # Exercise the payload after extraction too: permissions/symlinks are part of the product.
        suffix = '.zip' if sys.platform == 'win32' else '.tar.gz'
        step('archive-verify', python('verify_distribution.py', bundle, '--archive', output_dir / (name + suffix),
                                      '--report', reports / 'archive.json'))
        for filename in ('build-info.json', 'SHA256SUMS.json'):
            (output_dir / (name + '-' + filename)).write_bytes((bundle / filename).read_bytes())
        status['artifacts'] = {path.name: sha256(path) for path in sorted(output_dir.glob(name + '*')) if path.is_file()}
        status['success'] = True
        print(f'Complete: {output_dir}\nReport: {status_path}', flush=True)
    except BaseException as error:
        if status['stages'] and status['stages'][-1]['status'] == 'running':
            status['stages'][-1]['status'] = 'failed'
        status['error'] = str(error)
        raise
    finally:
        save()
    return status_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    parser.add_argument('--reuse-bundle', action='store_true')
    parser.add_argument('--skip-tests', action='store_true', help='Record that source tests were skipped; payload checks still run')
    parser.add_argument('--offline-tools', action='store_true', help='Require checksum-pinned tools already cached in build/')
    parser.add_argument('--tools-manifest', type=Path, help='Explicit Linux AppImage tool pins')
    args = parser.parse_args()
    try:
        run_release(args.output_dir, reuse_bundle=args.reuse_bundle,
                    skip_tests=args.skip_tests, offline_tools=args.offline_tools,
                    tools_manifest=args.tools_manifest.resolve() if args.tools_manifest else None)
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
