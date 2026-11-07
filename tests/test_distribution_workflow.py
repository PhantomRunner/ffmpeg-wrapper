"""Parse CI YAML and check that both jobs invoke the reviewed local entry points."""
from pathlib import Path

import yaml


def test_distribution_workflow_uses_shared_native_commands_and_keeps_failure_reports():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load((root / '.github/workflows/distribution.yml').read_text(), Loader=yaml.BaseLoader)
    assert workflow['on']['push']['branches'] == ['main']
    assert 'workflow_dispatch' in workflow['on']
    linux, windows = workflow['jobs']['linux'], workflow['jobs']['windows']
    assert linux['runs-on'] == 'ubuntu-24.04'
    assert windows['runs-on'] == 'windows-2022'
    assert any('scripts/build_appimage.sh --output-dir dist/linux-x86_64' in step.get('run', '') for step in linux['steps'])
    assert any('scripts/build_windows.ps1' in step.get('run', '') for step in windows['steps'])
    for job in (linux, windows):
        uploads = [step for step in job['steps'] if step.get('uses') == 'actions/upload-artifact@v4']
        assert len(uploads) == 2
        assert uploads[0]['if'] == 'always()'
        assert 'reports/**' in uploads[0]['with']['path']
        assert all(step['with']['retention-days'] == '14' for step in uploads)
        assert 'success()' in uploads[1]['if']


def test_regular_ci_installs_the_pinned_verification_tools():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load((root / '.github/workflows/tests.yml').read_text(), Loader=yaml.BaseLoader)
    assert any('packaging/test-requirements.txt' in step.get('run', '')
               for step in workflow['jobs']['test']['steps'])
