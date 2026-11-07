"""Exercise the AppImage shell workflow without Docker, downloads or native builds."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / 'scripts/build_appimage.sh'
pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux AppImage shell workflow')

FAKE_TOOL = '''
import json
import os
import subprocess
import sys
from pathlib import Path

tool, arguments = sys.argv[1], sys.argv[2:]
if tool == 'docker':
    stage = 'docker:' + arguments[0]
else:
    stage = {
        'scripts/build_release.py': 'release',
        'scripts/verify_linux_runtime.py': 'runtime',
    }[arguments[0]]
with Path(os.environ['FAKE_LOG']).open('a') as stream:
    stream.write(json.dumps({'stage': stage, 'args': arguments}) + '\\n')
if stage == os.environ.get('FAIL_STAGE'):
    raise SystemExit(29)
if stage == 'docker:run':
    image = next(i for i, arg in enumerate(arguments) if arg.startswith('media-wrapper-'))
    raise SystemExit(subprocess.run(arguments[image + 1:], cwd=os.environ['FAKE_REPOSITORY']).returncode)
'''


@pytest.fixture
def build_script(tmp_path):
    repository = tmp_path / 'project with spaces ü'
    scripts = repository / 'scripts'
    scripts.mkdir(parents=True)
    script = scripts / SCRIPT.name
    shutil.copy2(SCRIPT, script)
    binaries = tmp_path / 'fake executables'
    binaries.mkdir()
    for name in ('cat', 'dirname', 'id', 'sh', 'mkdir', 'mktemp', 'tee'):
        (binaries / name).symlink_to(shutil.which(name))
    uname = binaries / 'uname'
    uname.write_text('#!/bin/sh\ncase "$1" in\n-s) printf "%s\\n" "${FAKE_OS:-Linux}";;\n-m) printf "%s\\n" "${FAKE_ARCH:-x86_64}";;\nesac\n')
    uname.chmod(0o755)
    implementation = tmp_path / 'fake_tool.py'
    implementation.write_text(FAKE_TOOL)
    for name in ('docker', 'python', 'python3'):
        executable = binaries / name
        executable.write_text('#!/bin/sh\nexec "$SCRIPT_TEST_PYTHON" "$FAKE_TOOL_IMPLEMENTATION" '
                              + name + ' "$@"\n')
        executable.chmod(0o755)
    caller = tmp_path / 'unrelated caller'
    caller.mkdir()
    log = tmp_path / 'commands.jsonl'
    environment = dict(os.environ, PATH=str(binaries), SCRIPT_TEST_PYTHON=sys.executable,
                       FAKE_TOOL_IMPLEMENTATION=str(implementation), FAKE_LOG=str(log),
                       FAKE_REPOSITORY=str(repository))
    bash = shutil.which('bash')

    def run(*arguments, **extra_environment):
        return subprocess.run([bash, str(script), *arguments], cwd=caller,
                              env={**environment, **extra_environment}, capture_output=True,
                              text=True, timeout=10, check=False)

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    return SimpleNamespace(repository=repository, binaries=binaries, run=run, calls=calls)


def test_help_does_not_require_docker(build_script):
    (build_script.binaries / 'docker').unlink()
    result = build_script.run('--help')
    assert result.returncode == 0
    assert '--reuse-bundle' in result.stdout and '--skip-image-build' in result.stdout
    assert build_script.calls() == []


def test_default_build_runs_every_stage_with_compatible_container(build_script):
    result = build_script.run()
    assert result.returncode == 0, result.stderr
    calls = build_script.calls()
    assert [call['stage'] for call in calls] == [
        'docker:info', 'docker:build', 'docker:run', 'release',
        'docker:build', 'docker:run', 'runtime', 'docker:build', 'docker:run', 'runtime']
    assert calls[1]['args'] == ['build', '--build-arg', 'BASE_IMAGE=python:3.11-slim-bullseye',
                              '--target', 'builder', '--tag', 'media-wrapper-builder:compat',
                              str(build_script.repository)]
    invocation = calls[2]['args']
    assert invocation[invocation.index('--user') + 1] == f'{os.getuid()}:{os.getgid()}'
    assert invocation[invocation.index('--volume') + 1] == f'{build_script.repository}:/work'
    assert invocation[invocation.index('--workdir') + 1] == '/work'
    assert invocation[invocation.index('--env') + 1] == 'HOME=/tmp'
    assert calls[3]['args'] == ['scripts/build_release.py', '--output-dir', '/distribution']
    assert calls[4]['args'][2] == 'BASE_IMAGE=python:3.11-slim-bullseye'
    assert calls[7]['args'][2] == 'BASE_IMAGE=ubuntu:22.04'
    report, = (build_script.repository / 'dist/reports').glob('bootstrap-*/release-status.json')
    assert json.loads(report.read_text()) == {'success': True, 'stage': 'complete'}


@pytest.mark.parametrize('skip_image_build', [False, True])
def test_reuse_verifies_existing_bundle_without_rebuilding(build_script, skip_image_build):
    bundle = build_script.repository / 'dist/MediaWrapper'
    bundle.mkdir(parents=True)
    marker = bundle / 'previous-build.txt'
    marker.write_text('preserve this build')
    arguments = ['--reuse-bundle'] + (['--skip-image-build'] if skip_image_build else [])
    result = build_script.run(*arguments)
    assert result.returncode == 0, result.stderr
    stages = [call['stage'] for call in build_script.calls()]
    assert stages == ['docker:info'] + ([] if skip_image_build else ['docker:build']) + [
        'docker:run', 'release'] + ([] if skip_image_build else ['docker:build']) + [
        'docker:run', 'runtime'] + ([] if skip_image_build else ['docker:build']) + ['docker:run', 'runtime']
    release = next(call for call in build_script.calls() if call['stage'] == 'release')
    assert '--reuse-bundle' in release['args']
    assert marker.read_text() == 'preserve this build'


def test_existing_bundle_is_preserved_before_docker_starts(build_script):
    bundle = build_script.repository / 'dist/MediaWrapper'
    bundle.mkdir(parents=True)
    marker = bundle / 'keep.txt'
    marker.write_text('untouched')
    result = build_script.run()
    assert result.returncode != 0
    assert '--reuse-bundle' in result.stderr
    assert marker.read_text() == 'untouched'
    assert build_script.calls() == []


def test_existing_container_image_can_build_a_fresh_bundle(build_script):
    result = build_script.run('--skip-image-build')
    assert result.returncode == 0, result.stderr
    assert [call['stage'] for call in build_script.calls()] == [
        'docker:info', 'docker:run', 'release', 'docker:run', 'runtime', 'docker:run', 'runtime']


def test_reuse_requires_existing_bundle(build_script):
    result = build_script.run('--reuse-bundle')
    assert result.returncode != 0
    assert 'No portable bundle' in result.stderr
    assert build_script.calls() == []


@pytest.mark.parametrize('stage', ['docker:info', 'docker:build', 'docker:run', 'release'])
def test_failed_stage_stops_the_pipeline(build_script, stage):
    result = build_script.run(FAIL_STAGE=stage)
    assert result.returncode == 29
    stages = ['docker:info', 'docker:build', 'docker:run', 'release']
    assert [call['stage'] for call in build_script.calls()] == stages[:stages.index(stage) + 1]
    report, = (build_script.repository / 'dist/reports').glob('bootstrap-*/release-status.json')
    assert json.loads(report.read_text())['success'] is False


def test_missing_docker_is_reported(build_script):
    (build_script.binaries / 'docker').unlink()
    result = build_script.run()
    assert result.returncode != 0
    assert 'Docker is required' in result.stderr
    assert build_script.calls() == []


def test_unknown_flag_fails_without_starting_tools(build_script):
    result = build_script.run('--unknown')
    assert result.returncode == 2
    assert 'Unknown option' in result.stderr
    assert build_script.calls() == []


def test_custom_absolute_output_and_offline_flags_reach_native_command(build_script, tmp_path):
    output = tmp_path / 'output with spaces ü'
    result = build_script.run('--output-dir', str(output), '--offline-tools', '--skip-tests', '--skip-image-build',
                              '--tools-manifest', 'packaging/explicit.json')
    assert result.returncode == 0, result.stderr
    invocation = next(call for call in build_script.calls() if call['stage'] == 'docker:run')['args']
    assert str(output) + ':/distribution' in invocation
    release = next(call for call in build_script.calls() if call['stage'] == 'release')['args']
    assert '--offline-tools' in release and '--skip-tests' in release
    assert release[-2:] == ['--tools-manifest', '/work/packaging/explicit.json']


def test_output_option_requires_value(build_script):
    assert build_script.run('--output-dir').returncode == 2
    assert build_script.calls() == []


@pytest.mark.parametrize('environment', [{'FAKE_OS': 'Darwin'}, {'FAKE_ARCH': 'aarch64'}])
def test_unsupported_platform_is_rejected(build_script, environment):
    result = build_script.run(**environment)
    assert result.returncode != 0
    assert 'requires Linux x86-64' in result.stderr
    assert build_script.calls() == []
