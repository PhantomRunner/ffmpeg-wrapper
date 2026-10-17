"""Immutable per-build capability inventory; listing is not runtime proof."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BuildCapabilities:
    identity: tuple[str, int, int, str]
    version: str
    configuration: str
    encoders: frozenset[str]
    hwaccels: tuple[str, ...]
    encoder_help: tuple[tuple[str, str], ...]

from enum import Enum

GPU_ENCODERS = {
    'h264_nvenc': 'h264', 'hevc_nvenc': 'hevc',
    'h264_qsv': 'h264', 'hevc_qsv': 'hevc',
    'h264_amf': 'h264', 'hevc_amf': 'hevc',
    'h264_vaapi': 'h264', 'hevc_vaapi': 'hevc',
}

class EncoderStatus(str, Enum):
    UNKNOWN = 'Unknown'
    LISTED = 'Listed; not tested'
    WORKING = 'Runtime tested'
    UNAVAILABLE = 'Unavailable'


@dataclass(frozen=True)
class EncoderCapability:
    name: str
    listed: bool
    status: EncoderStatus
    detail: str = ''
    device: str | None = None


@dataclass(frozen=True)
class CapabilityReport:
    build: BuildCapabilities
    gpu: tuple[EncoderCapability, ...]

    def working(self) -> frozenset[str]:
        return frozenset(c.name for c in self.gpu if c.status == EncoderStatus.WORKING)
