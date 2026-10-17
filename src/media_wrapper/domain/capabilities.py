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
