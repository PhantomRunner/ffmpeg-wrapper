"""Compatibility alias for callers; policy is owned by the container registry."""
from media_wrapper.domain.containers import CONTAINERS

ALLOWED = {container: spec.codecs for container, spec in CONTAINERS.items()}
