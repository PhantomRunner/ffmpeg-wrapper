import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('build_appimage', Path(__file__).parents[1] / 'scripts/build_appimage.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.skipif(__import__('sys').platform != 'linux', reason='Linux AppRun shell launcher')
def test_appdir_checksums_spaces_arguments_and_no_overwrite(tmp_path):
    bundle = tmp_path / 'payload'
    bundle.mkdir()
    executable = bundle / 'MediaWrapper'
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    executable.chmod(0o755)
    (bundle / 'SHA256SUMS.json').write_text(json.dumps({'MediaWrapper': hashlib.sha256(executable.read_bytes()).hexdigest()}))
    icon = tmp_path / 'icon.svg'
    icon.write_text('<svg/>')
    target = tmp_path / 'App Dir ü'
    module.assemble_appdir(bundle, target, icon)
    result = subprocess.run([str(target / 'AppRun'), 'space name', '$literal', 'кириллица'],
                            check=True, text=True, capture_output=True)
    assert result.stdout.splitlines() == ['space name', '$literal', 'кириллица']
    assert (target / '.DirIcon').is_symlink()
    with pytest.raises(ValueError, match='already exists'):
        module.assemble_appdir(bundle, target, icon)
    executable.write_text('corrupt')
    with pytest.raises(ValueError, match='checksum'):
        module.assemble_appdir(bundle, tmp_path / 'bad', icon)
