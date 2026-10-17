"""Archive the full folder; tar preserves the Linux bundle's symbolic links."""
import platform
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
name = root / 'dist' / f'MediaWrapper-{platform.system()}-{platform.machine()}'
archive_format = 'zip' if platform.system() == 'Windows' else 'gztar'
suffix = '.zip' if archive_format == 'zip' else '.tar.gz'
if name.with_name(name.name + suffix).exists():
    raise SystemExit('Archive already exists; preserve or remove it explicitly')
print(shutil.make_archive(str(name), archive_format, root_dir=root / 'dist', base_dir='MediaWrapper'))
