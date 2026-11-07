"""Package a native payload, optionally fetch pinned tools and verify the image."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from distribution_common import artifact_name, verify_manifest

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare_tools(directory: Path, pins: dict, *, download: bool = False) -> dict[str, Path]:
    tools = {}
    for key, pin in pins.items():
        path = directory.resolve() / pin['name']
        if not path.exists() and download:
            directory.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                request = urllib.request.Request(pin['url'], headers={'User-Agent': 'MediaWrapper-AppImage-builder'})
                with tempfile.NamedTemporaryFile(dir=directory, prefix='.appimage-download-', delete=False) as stream:
                    temporary = Path(stream.name)
                    with urllib.request.urlopen(request, timeout=30) as response:
                        shutil.copyfileobj(response, stream)
                if digest(temporary) != pin['sha256']:
                    raise SystemExit(f'Download checksum mismatch for {key}; review packaging/appimage-tools.json before retrying')
                # A hard link publishes the complete, verified file atomically
                # without overwriting a file created by another builder.
                temporary.chmod(0o755)
                os.link(temporary, path)
            except (OSError, urllib.error.URLError) as error:
                raise SystemExit(f'Could not prepare {key}: {error}') from error
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        if not path.is_file() or digest(path) != pin['sha256']:
            raise SystemExit(f'Missing or mismatched {key}; supply the pinned file from {pin["url"]}')
        if not os.access(path, os.X_OK):
            path.chmod(path.stat().st_mode | 0o100)
        tools[key] = path
    return tools


def assemble_appdir(bundle: Path, destination: Path, icon: Path) -> None:
    if destination.exists():
        raise ValueError('AppDir already exists')
    verify_manifest(bundle)
    payload = destination / 'usr/lib/media-wrapper'
    shutil.copytree(bundle, payload, symlinks=True)
    launcher = destination / 'AppRun'
    launcher.write_text('#!/bin/sh\nHERE=${0%/*}\n[ "$HERE" != "$0" ] || HERE=.\n'
                        'HERE=$(CDPATH= cd -- "$HERE" && pwd) || exit 1\n'
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
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    parser.add_argument('--tools-manifest', type=Path, default=ROOT / 'packaging/appimage-tools.json',
                        help='Explicit tool pins; defaults to the versioned releases (no automatic cache fallback)')
    parser.add_argument('--tools', type=Path, default=ROOT / 'build/appimage-tools')
    parser.add_argument('--download-tools', action='store_true', help='Download missing tools and check their pinned SHA-256 hashes')
    parser.add_argument('--tools-only', action='store_true', help='Prepare tools without assembling an AppImage')
    parser.add_argument('--verify', action='store_true', help='Run installation and media checks on the generated AppImage')
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise SystemExit('This recipe requires native Linux x86_64')
    pins = json.loads(args.tools_manifest.read_text(encoding='utf-8'))
    tools = prepare_tools(args.tools, pins, download=args.download_tools)
    if args.tools_only:
        print(args.tools.resolve())
        return
    output_dir = args.output_dir.resolve()
    bundle = output_dir / 'MediaWrapper'
    info = json.loads((bundle / 'build-info.json').read_text())
    if info.get('target_os', 'Linux') != 'Linux':
        raise SystemExit('AppImage requires a Linux payload')
    output = output_dir / (artifact_name(ROOT, info) + '.AppImage')
    checksum = output.with_name(output.name + '.sha256')
    metadata = output.with_name(output.name + '.build.json')
    if any(path.exists() for path in (output, checksum, metadata)):
        raise SystemExit('AppImage or metadata already exists; preserve it explicitly before rebuilding')
    staging_root = output_dir / '.build'
    staging_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='appimage-', dir=staging_root) as staging:
        appdir = Path(staging) / 'MediaWrapper.AppDir'
        assemble_appdir(bundle, appdir, ROOT / 'src/media_wrapper/resources/icon.svg')
        subprocess.run([str(tools['tool']), '--appimage-extract-and-run', '--no-appstream',
                        '--runtime-file', str(tools['runtime']), str(appdir), str(output)],
                       env=dict(os.environ, ARCH='x86_64'), check=True)
    output.chmod(0o755)
    checksum.write_text(f'{digest(output)}  {output.name}\n', encoding='utf-8')
    metadata.write_text(json.dumps({'payload': info, 'appimage_tools': pins,
                                   'tools_manifest_sha256': digest(args.tools_manifest),
                                   'signed': False, 'build_platform': platform.platform()},
                                  indent=2), encoding='utf-8')
    if args.verify:
        subprocess.run([sys.executable, str(ROOT / 'scripts/verify_distribution.py'),
                        str(bundle), '--appimage', str(output)], check=True)
    print(output)


if __name__ == '__main__':
    main()
