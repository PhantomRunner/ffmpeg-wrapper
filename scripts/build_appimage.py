"""Package a verified native payload without fetching tools or changing system paths."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def assemble_appdir(bundle: Path, destination: Path, icon: Path) -> None:
    if destination.exists():
        raise ValueError('AppDir already exists')
    manifest = json.loads((bundle / 'SHA256SUMS.json').read_text(encoding='utf-8'))
    for name, expected in manifest.items():
        if digest(bundle / name) != expected:
            raise ValueError(f'Payload checksum mismatch: {name}')
    payload = destination / 'usr/lib/media-wrapper'
    shutil.copytree(bundle, payload, symlinks=True)
    launcher = destination / 'AppRun'
    launcher.write_text('#!/bin/sh\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1\n'
                        'exec "$HERE/usr/lib/media-wrapper/MediaWrapper" "$@"\n', encoding='utf-8')
    launcher.chmod(0o755)
    shutil.copy2(icon, destination / 'media-wrapper.svg')
    (destination / '.DirIcon').symlink_to('media-wrapper.svg')
    (destination / 'media-wrapper.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName=Media Wrapper\n'
        'Comment=Inspect, remux, convert and compress media\n'
        'Exec=AppRun\nIcon=media-wrapper\nTerminal=false\nCategories=AudioVideo;Video;\n',
        encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--tools', type=Path, default=ROOT / 'build/appimage-tools')
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise SystemExit('This recipe requires native Linux x86_64')
    pins = json.loads((ROOT / 'packaging/appimage-tools.json').read_text())
    tools = {}
    for key, pin in pins.items():
        path = args.tools.resolve() / pin['name']
        if not path.is_file() or digest(path) != pin['sha256']:
            raise SystemExit(f'Missing or mismatched {key}; supply the pinned file from {pin["url"]}')
        tools[key] = path
    bundle = ROOT / 'dist/MediaWrapper'
    info = json.loads((bundle / 'build-info.json').read_text())
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    identity = info['commit'][:12] + ('-dirty' if info['source_dirty'] else '')
    output = ROOT / 'dist' / f'MediaWrapper-{version}-Linux-x86_64-{identity}.AppImage'
    checksum = output.with_name(output.name + '.sha256')
    metadata = output.with_name(output.name + '.build.json')
    if any(path.exists() for path in (output, checksum, metadata)):
        raise SystemExit('AppImage or metadata already exists; preserve it explicitly before rebuilding')
    with tempfile.TemporaryDirectory(prefix='appimage-', dir=ROOT / 'build') as staging:
        appdir = Path(staging) / 'MediaWrapper.AppDir'
        assemble_appdir(bundle, appdir, ROOT / 'src/media_wrapper/resources/icon.svg')
        subprocess.run([str(tools['tool']), '--appimage-extract-and-run', '--no-appstream',
                        '--runtime-file', str(tools['runtime']), str(appdir), str(output)],
                       env=dict(os.environ, ARCH='x86_64'), check=True)
    output.chmod(0o755)
    checksum.write_text(f'{digest(output)}  {output.name}\n', encoding='utf-8')
    metadata.write_text(json.dumps({'payload': info, 'appimage_tools': pins,
                                   'signed': False, 'build_platform': platform.platform()},
                                  indent=2), encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
