"""Conservative container support policy, not encoder availability."""
from media_wrapper.domain.remux import Container

# Intentionally limited first slice; unlisted codecs require a later policy update.
ALLOWED = {
    Container.MP4: {'video': {'h264', 'hevc', 'av1', 'mpeg4'},
                    'audio': {'aac', 'mp3', 'ac3', 'eac3', 'alac'},
                    'subtitle': {'mov_text'}},
    Container.MATROSKA: {'video': {'h264', 'hevc', 'av1', 'vp8', 'vp9', 'mpeg4', 'mpeg2video', 'ffv1'},
                         'audio': {'aac', 'mp3', 'ac3', 'eac3', 'flac', 'opus', 'vorbis', 'pcm_s16le'},
                         'subtitle': {'subrip', 'ass', 'ssa', 'webvtt', 'hdmv_pgs_subtitle', 'dvd_subtitle'}},
}

