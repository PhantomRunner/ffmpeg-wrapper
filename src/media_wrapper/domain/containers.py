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


def codecs(**kinds: str) -> dict[str, frozenset[str]]:
    return {kind: frozenset(names.split()) for kind, names in kinds.items()}


CONTAINERS = {
    Container.MATROSKA: ContainerSpec('Matroska', 'matroska', '.mkv', codecs(
        video='h264 hevc av1 vp8 vp9 mpeg4 mpeg2video ffv1',
        audio='aac mp3 ac3 eac3 flac opus vorbis pcm_s16le',
        subtitle='subrip ass ssa webvtt hdmv_pgs_subtitle dvd_subtitle')),
    Container.MP4: ContainerSpec('MP4', 'mp4', '.mp4', codecs(
        video='h264 hevc av1 mpeg4', audio='aac mp3 ac3 eac3 alac', subtitle='mov_text')),
    Container.MOV: ContainerSpec('QuickTime MOV', 'mov', '.mov', codecs(
        video='h264 hevc mpeg4', audio='aac alac pcm_s16le', subtitle='mov_text')),
    Container.WEBM: ContainerSpec('WebM', 'webm', '.webm', codecs(
        video='vp8 vp9 av1', audio='opus vorbis'), chapters=False),
    Container.WAV: ContainerSpec('WAVE audio', 'wav', '.wav', codecs(audio='pcm_s16le'),
                                 chapters=False, max_streams=1),
    Container.FLAC: ContainerSpec('FLAC audio', 'flac', '.flac', codecs(audio='flac'),
                                  chapters=False, max_streams=1),
}
