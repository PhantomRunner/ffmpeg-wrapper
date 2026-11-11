"""Conservative muxer registry; availability is checked against the selected build."""
from dataclasses import dataclass

from media_wrapper.domain.remux import Container


@dataclass(frozen=True)
class ContainerSpec:
    label: str
    muxer: str
    extension: str
    codecs: dict[str, frozenset[str]]
    chapters: bool = True
    max_streams: int | None = None
    audio_only: bool = False
    artwork: bool = False


def codecs(**kinds: str) -> dict[str, frozenset[str]]:
    return {kind: frozenset(names.split()) for kind, names in kinds.items()}


CONTAINERS = {
    Container.MATROSKA: ContainerSpec('Matroska', 'matroska', '.mkv', codecs(
        video='h264 hevc av1 vp8 vp9 mpeg4 mpeg2video ffv1 dnxhd prores mjpeg png',
        audio='aac mp3 ac3 eac3 flac opus vorbis pcm_s16le pcm_s24le pcm_s32le pcm_f32le',
        subtitle='subrip ass ssa webvtt hdmv_pgs_subtitle dvd_subtitle',
        attachment='ttf otf')),
    Container.MP4: ContainerSpec('MP4', 'mp4', '.mp4', codecs(
        video='h264 hevc av1 mpeg4 mjpeg png', audio='aac mp3 ac3 eac3 alac', subtitle='mov_text'), artwork=True),
    Container.MOV: ContainerSpec('QuickTime MOV', 'mov', '.mov', codecs(
        video='h264 hevc mpeg4 dnxhd prores mjpeg png', audio='aac alac pcm_s16le pcm_s24le pcm_s32le pcm_f32le',
        subtitle='mov_text'), artwork=True),
    Container.WEBM: ContainerSpec('WebM', 'webm', '.webm', codecs(
        video='vp8 vp9 av1', audio='opus vorbis', subtitle='webvtt'), chapters=False),
    Container.WAV: ContainerSpec('WAVE audio', 'wav', '.wav',
                                 codecs(audio='pcm_s16le pcm_s24le pcm_s32le pcm_f32le'),
                                 chapters=False, max_streams=1, audio_only=True),
    Container.FLAC: ContainerSpec('FLAC audio', 'flac', '.flac', codecs(audio='flac', video='mjpeg png'),
                                  chapters=False, max_streams=2, audio_only=True, artwork=True),
    Container.M4A: ContainerSpec('M4A audio', 'ipod', '.m4a', codecs(audio='aac alac', video='mjpeg png'),
                                 chapters=False, max_streams=2, audio_only=True, artwork=True),
    Container.MP3: ContainerSpec('MP3 audio', 'mp3', '.mp3', codecs(audio='mp3', video='mjpeg png'),
                                 chapters=False, max_streams=2, audio_only=True, artwork=True),
    Container.OPUS: ContainerSpec('Ogg Opus', 'opus', '.opus', codecs(audio='opus'),
                                  chapters=False, max_streams=1, audio_only=True),
}
