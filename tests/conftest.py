"""Run Qt tests without requiring a display server."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import subprocess

import pytest

from media_wrapper.application.media_service import MediaService
from media_wrapper.domain.operations import (
    MediaOperation,
    OperationPlan,
    OutputTarget,
    StreamSelection,
)
from media_wrapper.domain.remux import Container
from media_wrapper.infrastructure.ffmpeg.binary_resolver import resolve


@pytest.fixture
def sample(tmp_path):
    try:
        binaries = resolve()
    except (FileNotFoundError, RuntimeError) as error:
        pytest.skip(str(error))
    source = tmp_path/'source ü.wav'
    subprocess.run([str(binaries.ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=0.1',
                    '-n', str(source)], check=True, capture_output=True, timeout=15)
    media = MediaService(binaries).inspect(source)
    plan = OperationPlan(MediaOperation.REMUX, media, (StreamSelection(0),),
                         OutputTarget(tmp_path/'result.mkv', Container.MATROSKA))
    return binaries, plan


from dataclasses import replace

@pytest.fixture
def video_sample(sample, tmp_path):
    binaries, plan = sample
    source = tmp_path/'video ü.mkv'
    subprocess.run([str(binaries.ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=96x64:r=24:d=0.5',
                    '-i', str(plan.media.path), '-c:v', 'ffv1', '-c:a', 'copy', '-n', str(source)],
                   check=True, capture_output=True, timeout=15)
    return binaries, replace(plan, media=MediaService(binaries).inspect(source))

