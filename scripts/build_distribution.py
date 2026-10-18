"""Build a native portable folder; never downloads or bundles FFmpeg binaries."""
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if sys.platform not in {'linux', 'win32'}:
        raise SystemExit('Only native Linux and Windows builds are supported')
    from packaging.requirements import Requirement
    for line in (ROOT / 'packaging/requirements.txt').read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        requirement = Requirement(line)
        if requirement.marker is None or requirement.marker.evaluate():
            actual = importlib.metadata.version(requirement.name)
            if actual not in requirement.specifier:
                raise SystemExit(f'Build dependency mismatch: {requirement.name} {actual}; install packaging/requirements.txt')
    destination = ROOT / 'dist' / 'MediaWrapper'
    if destination.exists():
        raise SystemExit('dist/MediaWrapper already exists; move or remove your previous build explicitly')
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    os.environ.setdefault('PYTHONHASHSEED', '0')
    os.environ.setdefault('SOURCE_DATE_EPOCH', subprocess.run(['git', 'log', '-1', '--format=%ct'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip())
    from PySide6.QtGui import QGuiApplication, QIcon
    app = QGuiApplication.instance() or QGuiApplication([])
    icon = QIcon(str(ROOT / 'src/media_wrapper/resources/icon.svg'))
    (ROOT / 'build').mkdir(exist_ok=True)
    if not icon.pixmap(256, 256).save(str(ROOT / 'build/media-wrapper.ico')):
        raise SystemExit('Could not create executable icon')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
                    str(ROOT / 'packaging/MediaWrapper.spec')], cwd=ROOT, check=True)
    documents = destination / 'docs'
    documents.mkdir()
    for name in ('README.md', 'THIRD_PARTY_NOTICES.md', 'CHANGELOG.md'):
        shutil.copy2(ROOT / name, destination / name)
    for name in ('DISTRIBUTION.md', 'RELEASE_CHECKLIST.md'):
        shutil.copy2(ROOT / 'docs' / name, documents / name)
    # Retain license files supplied by the installed wheels without claiming this
    # inventory alone satisfies every distributor's licensing obligations.
    licenses = destination / 'licenses'
    packages = {}
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
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.split('\0')
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in tracked if name and (ROOT / name).is_file()}
    dirty = bool(subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, check=True, capture_output=True, text=True).stdout)
    manifest = {'source_dirty': dirty, 'source_sha256': source_hashes,
                'license_audit_required': True, 'missing_wheel_license_files': missing_license_files,
                'python': sys.version, 'platform': platform.platform(), 'machine': platform.machine(),
                'commit': commit, 'packages': packages, 'ffmpeg_bundled': False,
                'preview_media_libraries': [str(path.relative_to(destination)) for path in sorted(destination.rglob('*'))
                    if path.is_file() and any(name in path.name.lower() for name in ('avcodec', 'avformat', 'avutil', 'swresample', 'swscale', 'ffmpegmedia'))]}
    (destination / 'build-info.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    hashes = {str(path.relative_to(destination)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(destination.rglob('*')) if path.is_file()}
    (destination / 'SHA256SUMS.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    print(f'Built {destination}; {len(hashes)} files. Native verification is required before release.')
    del app


if __name__ == '__main__':
    main()
