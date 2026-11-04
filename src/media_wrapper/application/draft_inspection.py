"""Inspection snapshots retain source identity without changing the FFprobe service."""
from media_wrapper.application.media_service import MediaService


class DraftProbeService(MediaService):
    def __init__(self, binaries):
        super().__init__(binaries)
        self.fingerprints = {}

    def inspect(self, source, cancel_event=None):
        before = source.stat()
        media = super().inspect(source, cancel_event)
        after = source.stat()
        fingerprint = after.st_size, after.st_mtime_ns
        if (before.st_size, before.st_mtime_ns) != fingerprint:
            raise ValueError('Source changed during inspection. Inspect it again.')
        self.fingerprints[source] = fingerprint
        return media
