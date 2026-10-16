"""Human-readable inspection values without subprocess or widget dependencies."""
from media_wrapper.domain.media import MediaFile, MediaStream


def display(value: object | None) -> str:
    return 'unknown' if value is None else str(value)


def stream_values(stream: MediaStream) -> tuple[str, ...]:
    frame_size = f'{stream.width} × {stream.height}' if stream.width and stream.height else 'unknown'
    rate = str(stream.frame_rate) if stream.frame_rate is not None else 'unknown'
    return (display(stream.index), stream.kind, stream.codec, display(stream.language), display(stream.bit_rate),
            frame_size, rate, display(stream.sample_rate), display(stream.channels), display(stream.channel_layout))


def format_inspection(info: MediaFile) -> str:
    lines = [f'File: {info.path}', f'Container: {info.format_name}',
             f'Duration: {display(info.duration)} s', f'Size: {display(info.size_bytes)} bytes',
             f'Bitrate: {display(info.bit_rate)} bit/s']
    for stream in info.streams:
        values = stream_values(stream)
        lines.extend(['', f'Stream {values[0]}: {stream.kind} / {stream.codec}',
                      f'  Language: {values[3]}', f'  Bitrate: {values[4]} bit/s'])
        if stream.kind == 'video':
            lines.extend([f'  Frame size: {values[5]}', f'  Frame rate: {values[6]} fps'])
        elif stream.kind == 'audio':
            lines.extend([f'  Sample rate: {values[7]} Hz', f'  Channels: {values[8]}', f'  Layout: {values[9]}'])
        elif stream.kind == 'subtitle':
            lines.append(f'  Subtitle type: {stream.codec}')
    return '\n'.join(lines)
