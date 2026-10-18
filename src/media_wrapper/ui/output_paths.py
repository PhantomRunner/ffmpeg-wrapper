"""Output field suggestions only; application services retain final validation."""
from pathlib import Path

from media_wrapper.domain.containers import CONTAINERS
from media_wrapper.domain.remux import Container


def suggest_output_path(value: str, container: Container) -> str:
    """Change only the suffix on an explicit container change, never touch disk."""
    if not value.strip():
        return value
    path = Path(value)
    suffix = CONTAINERS[container].extension
    if path.suffix.lower() == suffix:
        return value
    try:
        return str(path.with_suffix(suffix))
    except ValueError:
        # Incomplete input (e.g. a filesystem root) stays available for validation.
        return value
