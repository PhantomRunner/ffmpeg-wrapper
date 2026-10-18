"""Archive a native bundle with source identity and an external SHA-256 checksum."""
import hashlib
import json
import platform
import shutil
import tomllib
from pathlib import Path


def archive_distribution(root: Path) -> Path:
    bundle = root / 'dist' / 'MediaWrapper'
    manifest = json.loads((bundle / 'build-info.json').read_text(encoding='utf-8'))
    version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    identity = manifest['commit'][:12] + ('-dirty' if manifest['source_dirty'] else '')
    name = root / 'dist' / f'MediaWrapper-{version}-{platform.system()}-{platform.machine()}-{identity}'
    archive_format = 'zip' if platform.system() == 'Windows' else 'gztar'
    suffix = '.zip' if archive_format == 'zip' else '.tar.gz'
    archive = name.with_name(name.name + suffix)
    checksum = archive.with_name(archive.name + '.sha256')
    if archive.exists() or checksum.exists():
        raise SystemExit('Archive/checksum already exists; preserve or remove it explicitly')
    shutil.make_archive(str(name), archive_format, root_dir=root / 'dist', base_dir='MediaWrapper')
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    checksum.write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    return archive


if __name__ == '__main__':
    print(archive_distribution(Path(__file__).resolve().parents[1]))
