from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import (
    EncodingProfile,
    MediaOperation,
    OperationPlan,
    OutputTarget,
    PlanValidationError,
    StreamSelection,
    ValidationCode,
)
from media_wrapper.domain.remux import Container


def test_immutable_plan_and_safe_defaults():
    plan = OperationPlan(MediaOperation.REMUX, MediaFile(Path('input')),
                         (StreamSelection(3),), OutputTarget(Path('out.mkv'), Container.MATROSKA))
    assert plan.streams[0].profile == EncodingProfile('copy', None)
    assert plan.output.execution_path == Path('out.mkv')
    with pytest.raises(FrozenInstanceError):
        plan.operation = MediaOperation.CONVERT
    error = PlanValidationError(ValidationCode.STREAM, 'Missing stream')
    assert error.code == ValidationCode.STREAM and str(error) == 'Missing stream'


@pytest.fixture
def plan(tmp_path):
    from media_wrapper.domain.media import MediaStream
    source = tmp_path/'source ü.wav'
    source.write_bytes(b'source')
    return OperationPlan(MediaOperation.REMUX, MediaFile(source, streams=(MediaStream(2, 'audio', 'aac'),)),
                         (StreamSelection(2),), OutputTarget(tmp_path/'out.mp4', Container.MP4))


def test_validation_and_existing_output(plan):
    from media_wrapper.application.operation_validation import (
        validate_paths,
        validate_plan,
    )
    validate_plan(plan)
    validate_paths(plan)
    plan.output.path.write_bytes(b'keep')
    with pytest.raises(PlanValidationError) as error:
        validate_paths(plan)
    assert error.value.code == ValidationCode.OUTPUT
    assert plan.output.path.read_bytes() == b'keep'


@pytest.mark.parametrize('streams,code', [
    ((), ValidationCode.STREAM),
    ((StreamSelection(4),), ValidationCode.STREAM),
    ((StreamSelection(2), StreamSelection(2)), ValidationCode.STREAM),
    ((StreamSelection(2, EncodingProfile('copy', 128000)),), ValidationCode.OPTION),
    ((StreamSelection(2, EncodingProfile('aac')),), ValidationCode.OPTION),
])
def test_invalid_selection_and_options(plan, streams, code):
    from dataclasses import replace

    from media_wrapper.application.operation_validation import validate_plan
    with pytest.raises(PlanValidationError) as error:
        validate_plan(replace(plan, streams=streams), frozenset({'aac'}))
    assert error.value.code == code


def test_deterministic_copy_command(plan, monkeypatch):
    from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
    monkeypatch.setattr(Path, 'resolve', lambda *a, **k: pytest.fail('Builder accessed filesystem'))
    expected = ['ffmpeg', '-hide_banner', '-nostdin', '-n', '-i', str(plan.media.path),
                '-map', '0:2', '-c', 'copy', '-map_metadata', '0', '-map_chapters', '0',
                '-map_metadata:s:0', '0:s:2', '-f', 'mp4', str(plan.output.path)]
    assert CommandBuilder().build(Path('ffmpeg'), plan) == expected
    assert CommandBuilder().build(Path('ffmpeg'), plan) == expected


def test_convert_command_requires_availability(plan):
    from dataclasses import replace

    from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
    converted = replace(plan, operation=MediaOperation.CONVERT,
                        streams=(StreamSelection(2, EncodingProfile('aac', 128000)),))
    with pytest.raises(PlanValidationError, match='unavailable'):
        CommandBuilder().build(Path('ffmpeg'), converted)
    command = CommandBuilder().build(Path('ffmpeg'), converted, frozenset({'aac'}))
    assert command[8:12] == ['-c:0', 'aac', '-b:0', '128000']
    assert command[-3:] == ['-f', 'mp4', str(plan.output.path)]


def test_staging_keeps_final_separate_and_refuses_collisions(plan):
    from media_wrapper.application.operation_service import (
        prepare_command,
        prepare_operation,
    )
    prepared, args = prepare_command(Path('ffmpeg'), plan)
    temporary = prepared.output.temporary_path
    assert temporary.parent == plan.output.path.parent
    assert temporary != plan.output.path
    assert args[-1] == str(temporary) and '-n' in args and '-y' not in args
    assert not temporary.exists() and not plan.output.path.exists()
    temporary.write_bytes(b'keep')
    with pytest.raises(PlanValidationError, match='exists'):
        prepare_operation(prepared)
    assert temporary.read_bytes() == b'keep'


@pytest.mark.parametrize('name', ['CON.mp4', 'bad?.mp4', 'out.mp4.', 'NUL.mp4', 'bad:out.mp4'])
def test_nonportable_output_names(plan, name):
    from dataclasses import replace

    from media_wrapper.application.operation_validation import validate_paths
    with pytest.raises(PlanValidationError):
        validate_paths(replace(plan, output=replace(plan.output, path=plan.output.path.with_name(name))))


@pytest.mark.parametrize('case', ['source', 'hardlink', 'missing', 'parent', 'suffix', 'container', 'codec', 'temporary'])
def test_unsafe_and_unsupported_plans(plan, case):
    from dataclasses import replace

    from media_wrapper.application.operation_service import prepare_operation
    from media_wrapper.domain.media import MediaStream
    output = plan.output
    if case == 'source':
        output = replace(output, path=plan.media.path)
    elif case == 'hardlink':
        output.path.hardlink_to(plan.media.path)
    elif case == 'missing':
        plan.media.path.unlink()
    elif case == 'parent':
        output = replace(output, path=output.path.parent/'missing'/'out.mp4')
    elif case == 'suffix':
        output = replace(output, path=output.path.with_suffix('.wav'))
    elif case == 'container':
        output = replace(output, container='avi')
    elif case == 'codec':
        plan = replace(plan, media=replace(plan.media, streams=(MediaStream(2, 'subtitle', 'subrip'),)))
    else:
        output = replace(output, temporary_path=output.path)
    with pytest.raises(PlanValidationError):
        prepare_operation(replace(plan, output=output))


@pytest.mark.parametrize('profile', [EncodingProfile('aac', 0), EncodingProfile('aac', True),
                                      EncodingProfile('aac', -1), EncodingProfile('ffv1'),
                                      EncodingProfile('-y')])
def test_invalid_encode_options(plan, profile):
    from dataclasses import replace

    from media_wrapper.domain.operation_policy import validate_plan
    with pytest.raises(PlanValidationError):
        validate_plan(replace(plan, operation=MediaOperation.CONVERT, streams=(StreamSelection(2, profile),)),
                      frozenset({'aac', 'ffv1'}))


def test_mixed_copy_encode_mapping_uses_output_positions(plan):
    from dataclasses import replace

    from media_wrapper.domain.media import MediaStream
    from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
    plan = replace(plan, operation=MediaOperation.CONVERT,
                   media=replace(plan.media, streams=(MediaStream(2, 'audio', 'aac'), MediaStream(9, 'video', 'h264'))),
                   streams=(StreamSelection(9), StreamSelection(2, EncodingProfile('aac', 96000))))
    args = CommandBuilder().build(Path('ffmpeg'), plan, frozenset({'aac'}))
    assert args[6:14] == ['-map', '0:9', '-map', '0:2', '-c:0', 'copy', '-c:1', 'aac']
    assert args[14:16] == ['-b:1', '96000']


def test_real_minimal_convert_and_staged_remux(tmp_path):
    import subprocess

    from media_wrapper.application.media_service import MediaService
    from media_wrapper.application.operation_service import prepare_command
    from media_wrapper.infrastructure.ffmpeg.binary_resolver import resolve
    try:
        binaries = resolve()
    except (FileNotFoundError, RuntimeError) as error:
        pytest.skip(str(error))
    source = tmp_path/'source ü audio.wav'
    subprocess.run([str(binaries.ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=0.1',
                    '-c:a', 'pcm_s16le', '-n', str(source)], check=True, capture_output=True, timeout=15)
    svc = MediaService(binaries)
    info = svc.inspect(source)
    # Verify availability against this exact binary; production discovery is M7.
    result = subprocess.run([str(binaries.ffmpeg), '-encoders'], check=True, capture_output=True, text=True, timeout=15)
    available = frozenset(line.split()[1] for line in result.stdout.splitlines() if len(line.split()) >= 2)
    for operation, profile, container, suffix, codec in [
        (MediaOperation.REMUX, EncodingProfile(), Container.MATROSKA, '.mkv', 'pcm_s16le'),
        (MediaOperation.CONVERT, EncodingProfile('aac', 96000), Container.MP4, '.mp4', 'aac'),
    ]:
        plan = OperationPlan(operation, info, (StreamSelection(0, profile),), OutputTarget(tmp_path/('out'+suffix), container))
        prepared, args = prepare_command(binaries.ffmpeg, plan, available_encoders=available)
        subprocess.run(args, check=True, capture_output=True, timeout=15)
        assert not plan.output.path.exists()
        assert svc.inspect(prepared.output.execution_path).streams[0].codec == codec
        before = prepared.output.execution_path.read_bytes()
        refusal = subprocess.run(args, check=False, capture_output=True, timeout=15)
        assert refusal.returncode != 0 or b'Not overwriting' in refusal.stderr or b'Exiting' in refusal.stderr
        assert prepared.output.execution_path.read_bytes() == before
