"""Resolve a paired FFmpeg/FFprobe installation without a shell."""
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


from media_wrapper.infrastructure.process_environment import external_environment


@dataclass(frozen=True)
class Binaries:
    ffmpeg: Path
    ffprobe: Path
    version: str


def _program(name: str) -> str:
    return name + (".exe" if sys.platform == "win32" else "")


def resolve(mode: str = "external", directory: str | Path | None = None) -> Binaries:
    """Select paired binaries. Bundled directory must be explicitly supplied.

    An external directory can override PATH; a directory is the folder containing
    both executable files. Both binaries must pass a real -version invocation.
    """
    if mode not in {"external", "bundled"}:
        raise ValueError("Mode must be 'external' or 'bundled'")
    if mode == "bundled" and directory is None:
        raise ValueError("Bundled mode requires a directory containing both binaries")

    paths: list[Path] = []
    for name in ("ffmpeg", "ffprobe"):
        if directory is not None:
            candidate = Path(directory).expanduser() / _program(name)
        else:
            found = shutil.which(_program(name))
            if not found:
                raise FileNotFoundError(f"{name} not found in PATH")
            candidate = Path(found)
        if not candidate.is_file():
            raise FileNotFoundError(f"Missing executable: {candidate}")
        paths.append(candidate.resolve())

    versions: list[str] = []
    for binary in paths:
        try:
            result = subprocess.run([str(binary), "-version"], capture_output=True,
                                    text=True, timeout=8, check=True, env=external_environment())
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Cannot run {binary}: {exc}") from exc
        versions.append(result.stdout.splitlines()[0] if result.stdout else "unknown")
    return Binaries(ffmpeg=paths[0], ffprobe=paths[1], version=f"{versions[0]} | {versions[1]}")


def sidecar_directory() -> Path:
    """Suggested location only; callers must explicitly select bundled mode."""
    root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[4]
    return root / 'ffmpeg' / 'bin'
