"""Inspect every shipped ELF's required glibc versions and resolve dependencies."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from distribution_common import verify_manifest

MAX_GLIBC = (2, 31)


def required_glibc(output: str) -> list[tuple[int, ...]]:
    # Definitions exported by a bundled library are not requirements of that file.
    needs = output.partition('Version needs section')[2]
    named = set(re.findall(r'Name: (GLIBC_[^\s]+)', needs))
    unsupported = {name for name in named if not re.fullmatch(r'GLIBC_\d+(?:\.\d+)+', name)}
    if unsupported:
        raise ValueError(f'Unsupported glibc requirements for the 2.31 baseline: {sorted(unsupported)}')
    return sorted({tuple(map(int, value.split('.')))
                   for value in re.findall(r'Name: GLIBC_(\d+(?:\.\d+)+)', needs)})


def verify(bundle: Path, appimage: Path | None = None) -> dict:
    if sys.platform != 'linux':
        raise ValueError('ELF compatibility verification requires Linux with binutils')
    verify_manifest(bundle)
    files = sorted(path for path in bundle.rglob('*') if path.is_file())
    if appimage:
        files.append(appimage)
    entries = {}
    seen = set()
    # Match the bootloader's loader path; a bare ldd would incorrectly look for
    # bundled Debian libraries (for example libffi.so.7) in the host OS only.
    loader_path = str(bundle / '_internal')
    if os.environ.get('LD_LIBRARY_PATH'):
        loader_path += os.pathsep + os.environ['LD_LIBRARY_PATH']
    environment = dict(os.environ, LC_ALL='C', LD_LIBRARY_PATH=loader_path)
    for path in files:
        if path.resolve() in seen:
            continue
        seen.add(path.resolve())
        with path.open('rb') as stream:
            if stream.read(4) != b'\x7fELF':
                continue
        if path.name == 'libc.so.6' or path.name.startswith('ld-linux'):
            raise ValueError(f'glibc and its loader must stay external: {path}')
        result = subprocess.run(['readelf', '--wide', '--version-info', str(path)],
                                env=environment, capture_output=True, text=True, check=True, timeout=30)
        versions = required_glibc(result.stdout)
        maximum = max(versions, default=(0, 0))
        if maximum > MAX_GLIBC:
            raise ValueError(f'{path} requires glibc {".".join(map(str, maximum))}; maximum allowed is 2.31')
        dependencies = subprocess.run(['ldd', str(path)], env=environment,
                                      capture_output=True, text=True, check=False, timeout=30)
        description = dependencies.stdout + dependencies.stderr
        if 'not found' in description or (dependencies.returncode and
                'not a dynamic executable' not in description and 'statically linked' not in description):
            raise ValueError(f'Unresolved runtime libraries for {path}:\n{description}')
        name = path.relative_to(bundle).as_posix() if path.is_relative_to(bundle) else path.name
        entries[name] = {'max_required_glibc': '.'.join(map(str, maximum)),
                         'dependencies': description.strip()}
    if not entries:
        raise ValueError('No ELF binaries found in the Linux payload')
    return {'success': True, 'glibc_limit': '2.31', 'loader_library_path': loader_path,
            'elf_count': len(entries), 'files': entries}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--appimage', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = verify(args.bundle.resolve(), args.appimage.resolve() if args.appimage else None)
    if args.report:
        with args.report.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps({'success': True, 'glibc_limit': report['glibc_limit'], 'elf_count': report['elf_count']}))
