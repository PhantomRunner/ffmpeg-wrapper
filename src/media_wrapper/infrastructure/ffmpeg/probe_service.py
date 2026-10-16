"""FFprobe JSON adapter. Never invokes a command shell."""
import json
import subprocess
from pathlib import Path

from media_wrapper.domain.media import MediaFile
from media_wrapper.infrastructure.ffmpeg.probe_parser import parse_probe


def inspect_media(ffprobe: Path, source: Path) -> MediaFile:
    source = source.expanduser().absolute()
    if not source.is_file():
        raise FileNotFoundError(f"File does not exist: {source}")
    args = [str(ffprobe), "-v", "error", "-show_format", "-show_streams",
            "-of", "json", str(source)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"FFprobe failed ({result.returncode})")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise ValueError("Unexpected FFprobe output")  # noqa: TRY004 - invalid JSON payload value
    return parse_probe(source, payload)
