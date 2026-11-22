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
    if info.tags:
        lines.extend(['', 'Container metadata', *(f'  {key}: {value}' for key, value in info.tags)])
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
        for label, value in (
            ('Title', stream.title), ('Profile', stream.profile), ('Pixel format', stream.pixel_format),
            ('Bit depth', stream.bit_depth), ('Sample aspect ratio', stream.sample_aspect_ratio),
            ('Display aspect ratio', stream.display_aspect_ratio), ('Color matrix', stream.color_space),
            ('Color primaries', stream.color_primaries), ('Color transfer', stream.color_transfer),
            ('Color range', stream.color_range), ('Duration (s)', stream.duration),
        ):
            if value is not None:
                lines.append(f'  {label}: {value}')
        if stream.dispositions:
            lines.append(f'  Dispositions: {", ".join(stream.dispositions)}')
        lines.extend(f'  {key}: {value}' for key, value in stream.tags if key.lower() not in ('title', 'language'))
        lines.extend(f'  Side data: {data}' for data in stream.side_data)
    if info.chapters:
        lines.extend(['', 'Chapters'])
        for chapter in info.chapters:
            lines.append(f'  {display(chapter.start)}–{display(chapter.end)} s · {chapter.title or "Untitled chapter"}')
    return '\n'.join(lines)
