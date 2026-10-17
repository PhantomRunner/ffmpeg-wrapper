"""A deliberately small output-option grammar, identical on Linux and Windows."""
LIMITS = {'-threads': (1, 64), '-max_muxing_queue_size': (1, 65536)}


def parse_custom_options(text: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(text, str) or len(text) > 256:
        raise ValueError('Custom options must be at most 256 characters')
    tokens = text.split()
    if len(tokens) % 2:
        raise ValueError('Custom options require flag/value pairs')
    pairs = tuple(zip(tokens[::2], tokens[1::2], strict=True))
    validate_custom_options(pairs)
    return pairs


def validate_custom_options(options: tuple[tuple[str, str], ...]) -> None:
    seen = set()
    for flag, value in options:
        if flag not in LIMITS or flag in seen:
            raise ValueError('Only one -threads and one -max_muxing_queue_size option are allowed')
        low, high = LIMITS[flag]
        if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or not low <= int(value) <= high:
            raise ValueError(f'{flag} requires an integer from {low} to {high}')
        seen.add(flag)
