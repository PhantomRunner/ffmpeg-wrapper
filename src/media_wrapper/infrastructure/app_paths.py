"""Native per-user locations; resolving paths does not create files."""
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QStandardPaths


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    data_dir: Path

    @property
    def settings_file(self) -> Path:
        return self.config_dir / 'settings.json'

    @property
    def log_file(self) -> Path:
        return self.data_dir / 'logs' / 'media-wrapper.log'


def resolve_app_paths() -> AppPaths:
    """Call after setting the QApplication name to MediaWrapper."""
    config = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    if not config or not data:
        raise OSError('The operating system did not provide per-user application directories')
    return AppPaths(Path(config), Path(data))
