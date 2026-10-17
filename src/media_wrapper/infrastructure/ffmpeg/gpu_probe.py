"""Short cancellable synthetic encode: listing an encoder is not runtime proof."""
from pathlib import Path
from subprocess import TimeoutExpired
from threading import Event

from media_wrapper.domain.capabilities import (
    GPU_ENCODERS,
    EncoderCapability,
    EncoderStatus,
)
from media_wrapper.domain.inspection import OperationCancelled
from media_wrapper.infrastructure.ffmpeg.probe_service import run_cancellable_probe


def gpu_probe_command(ffmpeg: Path, encoder: str, device: str | None = None) -> list[str]:
    if encoder not in GPU_ENCODERS:
        raise ValueError('Unsupported GPU encoder candidate')
    command = [str(ffmpeg), '-hide_banner', '-nostdin', '-v', 'error', '-n']
    if encoder.endswith('_vaapi'):
        if not device:
            raise ValueError('Select a VAAPI render device before testing')
        command.extend(['-vaapi_device', device])
    command.extend(['-f', 'lavfi', '-i', 'color=c=black:s=128x128:r=25:d=0.2', '-frames:v', '3', '-an'])
    if encoder.endswith('_vaapi'):
        command.extend(['-vf', 'format=nv12,hwupload'])
    else:
        command.extend(['-pix_fmt', 'nv12'])
    command.extend(['-c:v', encoder, '-f', 'null', '-'])
    return command


def test_gpu_encoder(ffmpeg: Path, encoder: str, event: Event, device: str | None = None) -> EncoderCapability:
    if encoder.endswith('_vaapi') and not device:
        return EncoderCapability(encoder, True, EncoderStatus.UNKNOWN, 'Choose a VAAPI render device to test', device)
    try:
        result = run_cancellable_probe(gpu_probe_command(ffmpeg, encoder, device), event, timeout=15)
        if result.returncode:
            return EncoderCapability(encoder, True, EncoderStatus.UNAVAILABLE,
                                     result.stderr[-4000:] or f'Runtime test exited {result.returncode}', device)
        return EncoderCapability(encoder, True, EncoderStatus.WORKING,
                                 'Synthetic 128×128 encode passed; real jobs may still fail', device)
    except OperationCancelled:
        raise
    except (OSError, RuntimeError, TimeoutError, TimeoutExpired) as error:
        return EncoderCapability(encoder, True, EncoderStatus.UNAVAILABLE, str(error), device)
