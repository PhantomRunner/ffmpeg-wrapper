"""Small, stdlib-only contracts shared by native packaging commands."""
import hashlib
import json
import platform
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(bundle: Path) -> dict:
    manifest = json.loads((bundle / 'SHA256SUMS.json').read_text(encoding='utf-8'))
    actual = {path.relative_to(bundle).as_posix() for path in bundle.rglob('*')
              if path.is_file() and path != bundle / 'SHA256SUMS.json'}
    if actual != set(manifest):
        raise ValueError(f'Payload inventory differs: missing={sorted(set(manifest) - actual)}, '
                         f'unexpected={sorted(actual - set(manifest))}')
    for name, expected in manifest.items():
        path = bundle / name
        if not path.resolve().is_relative_to(bundle.resolve()):
            raise ValueError(f'Unsafe payload manifest path: {name}')
        if sha256(path) != expected:
            raise ValueError(f'Payload checksum mismatch: {name}')
    return manifest


def artifact_name(root: Path, info: dict) -> str:
    import tomllib
    version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    identity = info['commit'][:12] + ('-dirty' if info['source_dirty'] else '')
    machine = info.get('machine', platform.machine()).lower()
    architecture = 'x86_64' if machine in {'amd64', 'x86_64'} else machine
    return f'MediaWrapper-{version}-{info.get("target_os", platform.system())}-{architecture}-{identity}'
