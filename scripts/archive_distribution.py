"""Archive a native bundle with source identity and an external SHA-256 checksum."""
import argparse
import json
import platform
import shutil
from pathlib import Path

from distribution_common import artifact_name, sha256, verify_manifest


def archive_distribution(root: Path, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or root / 'dist'
    bundle = output_dir / 'MediaWrapper'
    verify_manifest(bundle)
    manifest = json.loads((bundle / 'build-info.json').read_text(encoding='utf-8'))
    name = output_dir / artifact_name(root, manifest)
    archive_format = 'zip' if platform.system() == 'Windows' else 'gztar'
    suffix = '.zip' if archive_format == 'zip' else '.tar.gz'
    archive = name.with_name(name.name + suffix)
    checksum = archive.with_name(archive.name + '.sha256')
    if archive.exists() or checksum.exists():
        raise SystemExit('Archive/checksum already exists; preserve or remove it explicitly')
    shutil.make_archive(str(name), archive_format, root_dir=output_dir, base_dir='MediaWrapper')
    digest = sha256(archive)
    checksum.write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'dist')
    args = parser.parse_args()
    print(archive_distribution(Path(__file__).resolve().parents[1], args.output_dir.resolve()))
