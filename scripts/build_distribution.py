"""Build a native portable folder; never downloads or bundles FFmpeg binaries."""
import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from distribution_common import sha256

ROOT = Path(__file__).resolve().parents[1]


def copy_qt_license_texts(destination: Path) -> None:
    source = ROOT / 'packaging/licenses'
    inventory = json.loads((source / 'SOURCES.json').read_text(encoding='utf-8'))
    for name, expected in inventory['files_sha256'].items():
        if sha256(source / name) != expected:
            raise ValueError(f'Vendored license checksum mismatch: {name}')
    shutil.copytree(source, destination)


def check_environment() -> dict[str, str]:
    if sys.platform not in {'linux', 'win32'}:
        raise SystemExit('Only native Linux and Windows builds are supported')
    if sys.version_info[:2] != (3, 11):
        raise SystemExit('Distribution builds require Python 3.11; use the isolated build command')
    if platform.machine().lower() not in {'amd64', 'x86_64'} or sys.maxsize <= 2**32:
        raise SystemExit('Distribution builds require x86-64 Python and OS')
    if sys.platform == 'linux':
        libc, version = platform.libc_ver()
        if libc != 'glibc' or tuple(map(int, version.split('.'))) > (2, 31):
            raise SystemExit('Build Linux distributions in the Debian 11/glibc 2.31 Docker builder')
    from packaging.requirements import Requirement
    packages = {}
    for line in (ROOT / 'packaging/requirements.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        requirement = Requirement(line)
        if requirement.marker is None or requirement.marker.evaluate():
            try:
                actual = importlib.metadata.version(requirement.name)
            except importlib.metadata.PackageNotFoundError:
                raise SystemExit(f'Missing build dependency: {requirement.name}; install packaging/requirements.txt') from None
            if actual not in requirement.specifier:
                raise SystemExit(f'Build dependency mismatch: {requirement.name} {actual}; install packaging/requirements.txt')
            packages[requirement.name] = actual
    return packages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    packages = check_environment()
    output_dir = args.output_dir.resolve()
    destination = output_dir / 'MediaWrapper'
    if destination.exists():
        raise SystemExit(f'{destination} already exists; choose a new --output-dir or preserve your previous build explicitly')
    work = output_dir / '.build'
    work.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    os.environ.setdefault('PYTHONHASHSEED', '0')
    os.environ.setdefault('SOURCE_DATE_EPOCH', subprocess.run(['git', 'log', '-1', '--format=%ct'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip())
    from PySide6.QtGui import QGuiApplication, QIcon
    app = QGuiApplication.instance() or QGuiApplication([])
    icon = QIcon(str(ROOT / 'src/media_wrapper/resources/icon.svg'))
    icon_path = work / 'media-wrapper.ico'
    if not icon.pixmap(256, 256).save(str(icon_path)):
        raise SystemExit('Could not create executable icon')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
                    '--distpath', str(output_dir), '--workpath', str(work / 'pyinstaller'),
                    str(ROOT / 'packaging/MediaWrapper.spec')], cwd=ROOT, check=True,
                   env=dict(os.environ, MEDIA_WRAPPER_BUILD_ICON=str(icon_path)))
    for name in ('README.md', 'BUILDING.md'):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, destination / name)
    shutil.copy2(icon_path, destination / 'media-wrapper.ico')
    # Retain license files supplied by the installed wheels without claiming this
    # inventory alone satisfies every distributor's licensing obligations.
    licenses = destination / 'licenses'
    missing_license_files = []
    for name in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'pyinstaller'):
        distribution = importlib.metadata.distribution(name)
        packages[name] = distribution.version
        package_licenses = licenses / name
        package_licenses.mkdir(parents=True, exist_ok=True)
        (package_licenses / 'METADATA.txt').write_text(distribution.read_text('METADATA') or '', encoding='utf-8')
        copied = 0
        for item in distribution.files or ():
            if any(part.lower() in {'licenses', 'license', 'copying', 'copyright'} or part.lower().startswith(('license.', 'copying.')) for part in item.parts):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    target = licenses / name / str(item).replace('..', '_')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    copied += 1
        if not copied:
            missing_license_files.append(name)
    python_license = Path(sys.base_prefix) / ('LICENSE.txt' if sys.platform == 'win32' else f'lib/python{sys.version_info.major}.{sys.version_info.minor}/LICENSE.txt')
    if python_license.is_file():
        licenses.mkdir(exist_ok=True)
        shutil.copy2(python_license, licenses / 'Python-LICENSE.txt')
    # The 6.7.3 wheels declare LGPL in METADATA but contain no license text files.
    # Preserve the original metadata and supply the canonical, checked GNU texts.
    copy_qt_license_texts(licenses / 'Qt-PySide6-license-texts')
    (licenses / 'README.md').write_text(
        'Python and PyInstaller license files are copied from their installations.\n'
        'PySide6, Essentials, Addons and shiboken6 6.7.3 declare LGPL in METADATA.\n'
        'Their original wheel metadata is retained in each package directory.\n'
        'Canonical GPL-2, GPL-3 and LGPL-3 texts are in Qt-PySide6-license-texts;\n'
        'SOURCES.json records their origin and checksums. These texts supplement\n'
        'the wheel inventory; license_audit_required remains recorded in build-info.json.\n', encoding='utf-8')
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    tracked = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.split('\0')
    source_hashes = {name: sha256(ROOT / name) for name in sorted(set(tracked)) if name and (ROOT / name).is_file()}
    dirty = bool(subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, check=True, capture_output=True, text=True).stdout)
    manifest = {'source_dirty': dirty, 'source_sha256': source_hashes,
                'license_audit_required': True, 'missing_wheel_license_files': missing_license_files,
                'qt_license_texts': 'licenses/Qt-PySide6-license-texts',
                'python': sys.version, 'platform': platform.platform(), 'machine': platform.machine(),
                'target_os': platform.system(),
                'compatibility': {'python': '3.11', 'qt': '6.7.3', 'architecture': 'x86_64',
                                  'linux_glibc_max': '2.31', 'windows_min': '10.0.17763'},
                'build_libc': platform.libc_ver(),
                'environment_packages': dict(sorted((item.metadata['Name'], item.version) for item in importlib.metadata.distributions())),
                'commit': commit, 'packages': packages, 'ffmpeg_bundled': False,
                'preview_media_libraries': [str(path.relative_to(destination)) for path in sorted(destination.rglob('*'))
                    if path.is_file() and any(name in path.name.lower() for name in ('avcodec', 'avformat', 'avutil', 'swresample', 'swscale', 'ffmpegmedia'))]}
    (destination / 'build-info.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    hashes = {str(path.relative_to(destination)).replace('\\', '/'): sha256(path)
              for path in sorted(destination.rglob('*')) if path.is_file()}
    (destination / 'SHA256SUMS.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    print(f'Built {destination}; {len(hashes)} files. Native verification is required before release.')
    del app


if __name__ == '__main__':
    main()
