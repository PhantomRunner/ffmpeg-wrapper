# Build natively on each target OS: python scripts/build_distribution.py
import os
from pathlib import Path

root = Path(SPECPATH).parent
analysis = Analysis(
    [str(root / 'packaging' / 'launcher.py')], pathex=[str(root / 'src')],
    datas=[(str(root / 'src' / 'media_wrapper' / 'resources'), 'media_wrapper/resources')],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtPdf', 'PySide6.QtQml', 'PySide6.QtQuick'],
)
# Fusion styling keeps the optional GTK platform theme out of the runtime requirements.
analysis.binaries = [entry for entry in analysis.binaries if Path(entry[0]).name != 'libqgtk3.so']
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name='MediaWrapper',
          debug=False, strip=False, upx=False, console=False,
          icon=os.environ.get('MEDIA_WRAPPER_BUILD_ICON', str(root / 'build' / 'media-wrapper.ico')))
collection = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name='MediaWrapper')
