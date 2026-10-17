from threading import Event

from media_wrapper.infrastructure.ffmpeg.capabilities import discover_build, parse_hwaccels


def test_build_cache_and_binary_identity(tmp_path, monkeypatch):
    executable = tmp_path/'ffmpeg'
    executable.write_bytes(b'build1')
    calls = []
    def read(binary, args, event):
        calls.append(tuple(args))
        if args == ['-encoders']:
            return ' V....D libx264 H264\n V....D h264_nvenc NVIDIA'
        if args == ['-hwaccels']:
            return 'Hardware acceleration methods:\ncuda\nvaapi\n'
        return 'build details'
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.capabilities.read_binary', read)
    first = discover_build(executable, Event())
    calls.clear()
    assert discover_build(executable, Event()) is first
    assert calls == [('-version',)]
    assert first.hwaccels == ('cuda', 'vaapi')
    assert len(first.encoder_help) == 2
    executable.write_bytes(b'build two changed')
    assert discover_build(executable, Event()).identity != first.identity
    assert discover_build(executable, Event(), refresh=True) is not first


def test_hwaccel_parser():
    assert parse_hwaccels('Hardware acceleration methods:\ncuda\nvaapi\n\n') == ('cuda', 'vaapi')
