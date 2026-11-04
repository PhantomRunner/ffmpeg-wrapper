"""Wrap the verified native one-folder payload with the pinned Inno Setup compiler."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare_compiler(directory, pin):
    directory.mkdir(parents=True, exist_ok=True)
    installer = directory / pin['name']
    if not installer.exists():
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, prefix='.inno-download-', delete=False) as stream:
                temporary = Path(stream.name)
                with urllib.request.urlopen(pin['url'], timeout=60) as response:
                    shutil.copyfileobj(response, stream)
            with temporary.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != pin['sha256']:
                    raise ValueError('Downloaded Inno Setup checksum differs from its pin')
            os.link(temporary, installer)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    with installer.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != pin['sha256']:
            raise ValueError('Cached Inno Setup checksum differs from its pin; existing file preserved')
    compiler = directory / 'compiler/ISCC.exe'
    if not compiler.is_file():
        subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS',
                        '/DIR=' + str(compiler.parent.resolve())], check=True, timeout=120)
    if not compiler.is_file():
        raise ValueError('Inno Setup installation did not produce ISCC.exe')
    return compiler


def verify_payload(bundle):
    if not (bundle / 'MediaWrapper.exe').is_file():
        raise ValueError('Build and verify the native Windows payload first')
    manifest = json.loads((bundle / 'SHA256SUMS.json').read_text(encoding='utf-8'))
    for name, expected in manifest.items():
        path = bundle / name
        if not path.resolve().is_relative_to(bundle.resolve()):
            raise ValueError('Unsafe payload manifest path')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError(f'Payload checksum mismatch: {name}')
    info = json.loads((bundle / 'build-info.json').read_text(encoding='utf-8'))
    if 'Windows' not in info['platform'] or info.get('ffmpeg_bundled') is not False:
        raise ValueError('Expected a native Windows payload without processing FFmpeg executables')
    return info


def compiler_arguments(compiler, bundle, output_dir, name, version, icon):
    return [str(compiler), f'/DAppVersion={version}', f'/DPayloadDir={bundle.resolve()}',
            f'/DOutputBaseName={name}', f'/DAppIcon={icon.resolve()}', f'/O{output_dir.resolve()}',
            str(ROOT / 'packaging/MediaWrapper.iss')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', type=Path)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'dist/MediaWrapper')
    parser.add_argument('--prepare-compiler', action='store_true', help='Explicitly download, verify and install pinned build-only compiler into build/inno-tools')
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise SystemExit('Build Windows installers on a native Windows runner')
    pin = json.loads((ROOT / 'packaging/windows-installer-tools.json').read_text())
    if args.prepare_compiler:
        print(prepare_compiler(ROOT / 'build/inno-tools', pin))
        return
    compiler = args.compiler or Path(os.environ.get('INNO_COMPILER') or shutil.which('ISCC.exe') or '')
    if not compiler.is_file():
        raise SystemExit('Supply the pinned Inno Setup 7.1.1 compiler using --compiler or INNO_COMPILER')
    version_check = subprocess.run([str(compiler), '/?'], capture_output=True, text=True, check=False)
    if not re.search(r'\b' + re.escape(pin['version']) + r'\b', version_check.stdout + version_check.stderr):
        raise SystemExit('Inno Setup compiler version differs from the pinned tool')
    info = verify_payload(args.bundle)
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    identity = info['commit'][:12] + ('-dirty' if info['source_dirty'] else '')
    name = f'MediaWrapper-{version}-Windows-x86_64-{identity}-setup'
    output_dir = ROOT / 'dist'
    output = output_dir / (name + '.exe')
    metadata = output.with_suffix('.build.json')
    checksum = output.with_suffix('.exe.sha256')
    if any(path.exists() for path in (output, metadata, checksum)):
        raise SystemExit('Preserve the existing installer and metadata before building again')
    icon = ROOT / 'build/media-wrapper.ico'
    if not icon.is_file():
        raise SystemExit('The native payload build must generate build/media-wrapper.ico')
    subprocess.run(compiler_arguments(compiler, args.bundle, output_dir, name, version, icon), check=True)
    if not output.is_file():
        raise SystemExit('Compiler succeeded without producing the expected installer')
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    checksum.write_text(f'{digest}  {output.name}\n', encoding='utf-8')
    metadata.write_text(json.dumps({'payload': info, 'installer_tool': pin, 'signed': False}, indent=2), encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
