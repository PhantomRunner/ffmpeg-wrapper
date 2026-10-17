"""Selected-binary inventory, cached by executable identity and version."""
import re
from pathlib import Path
from threading import Event, Lock

from media_wrapper.domain.capabilities import BuildCapabilities
from media_wrapper.domain.operation_policy import ENCODERS
from media_wrapper.infrastructure.ffmpeg.encoders import parse_encoders
from media_wrapper.infrastructure.ffmpeg.probe_service import run_cancellable_probe

GPU_ENCODERS = {
    'h264_nvenc': 'h264', 'hevc_nvenc': 'hevc',
    'h264_qsv': 'h264', 'hevc_qsv': 'hevc',
    'h264_amf': 'h264', 'hevc_amf': 'hevc',
    'h264_vaapi': 'h264', 'hevc_vaapi': 'hevc',
}
_CACHE: dict[tuple, BuildCapabilities] = {}
_LOCK = Lock()


def read_binary(ffmpeg: Path, args: list[str], event: Event) -> str:
    result = run_cancellable_probe([str(ffmpeg), '-hide_banner', *args], event, timeout=15)
    if result.returncode:
        raise RuntimeError(f'Capability query failed: {result.stderr[-4000:]}')
    return result.stdout


def parse_hwaccels(text: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in text.splitlines() if re.fullmatch(r'[a-z0-9_]+', line.strip()))


def discover_build(ffmpeg: Path, event: Event, *, refresh: bool = False) -> BuildCapabilities:
    executable = ffmpeg.resolve(strict=True)
    stat = executable.stat()
    version = read_binary(executable, ['-version'], event)
    identity = (str(executable), stat.st_size, stat.st_mtime_ns, version)
    with _LOCK:
        if not refresh and identity in _CACHE:
            return _CACHE[identity]
    encoders = parse_encoders(read_binary(executable, ['-encoders'], event))
    help_text = tuple((name, read_binary(executable, ['-h', f'encoder={name}'], event))
                      for name in sorted(encoders & (set(ENCODERS) | set(GPU_ENCODERS))))
    build = BuildCapabilities(identity, version, read_binary(executable, ['-buildconf'], event), encoders,
                              parse_hwaccels(read_binary(executable, ['-hwaccels'], event)), help_text)
    current = executable.stat()
    if (current.st_size, current.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
        raise RuntimeError('FFmpeg changed during discovery; scan again')
    with _LOCK:
        # Bound the in-memory cache and discard older identities for this path.
        for key in list(_CACHE):
            if key[0] == str(executable):
                del _CACHE[key]
        if len(_CACHE) >= 8:
            _CACHE.clear()
        _CACHE[identity] = build
    return build
