import hashlib
import importlib.util
import json
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('archive_distribution', Path(__file__).parents[1] / 'scripts/archive_distribution.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_archive_identity_checksum_and_overwrite_protection(tmp_path, monkeypatch):
    monkeypatch.setattr(module.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    bundle = tmp_path / 'dist' / 'MediaWrapper'
    bundle.mkdir(parents=True)
    (bundle / 'build-info.json').write_text(json.dumps({'commit': 'a' * 40, 'source_dirty': False}))
    (bundle / 'MediaWrapper').write_bytes(b'executable fixture')
    (tmp_path / 'pyproject.toml').write_text('[project]\nversion = "0.1.0"\n')
    archive = module.archive_distribution(tmp_path)
    assert archive.name == 'MediaWrapper-0.1.0-Linux-x86_64-aaaaaaaaaaaa.tar.gz'
    with tarfile.open(archive) as content:
        assert content.extractfile('MediaWrapper/MediaWrapper').read() == b'executable fixture'
    checksum = archive.with_name(archive.name + '.sha256').read_text()
    assert checksum == hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n'
    before = archive.read_bytes()
    with pytest.raises(SystemExit, match='already exists'):
        module.archive_distribution(tmp_path)
    assert archive.read_bytes() == before
