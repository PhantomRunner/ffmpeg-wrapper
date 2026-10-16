"""Exercise the real entry point with isolated diagnostic locations."""
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize('file_logging', [True, False])
def test_entry_point_starts_and_closes_with_diagnostic_status(tmp_path, file_logging):
    script = '''
import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from media_wrapper import main
from media_wrapper.infrastructure.app_paths import AppPaths

root = Path(sys.argv[1])
file_logging = sys.argv[2] == 'True'
data = root / 'data'
if not file_logging:
    data.write_text('existing file')
main.resolve_app_paths = lambda: AppPaths(root / 'config', data)
OriginalWindow = main.MainWindow

class SmokeWindow(OriginalWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.observed_status = self.statusBar().currentMessage()
        QTimer.singleShot(10, self.finish_smoke)

    def finish_smoke(self):
        if self.thread is not None:
            QTimer.singleShot(10, self.finish_smoke)
            return
        expected = 'Diagnostic log:' if file_logging else 'File logging unavailable:'
        print(self.observed_status)
        if expected not in self.observed_status:
            QApplication.instance().exit(3)
        else:
            self.close()

main.MainWindow = SmokeWindow
raise SystemExit(main.main())
'''
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), str(file_logging)],
                            env=environment, capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    if file_logging:
        assert 'Diagnostic log:' in result.stdout
        text = (tmp_path/'data'/'logs'/'media-wrapper.log').read_text(encoding='utf-8')
        assert 'Application diagnostics initialized' in text
    else:
        assert 'File logging unavailable:' in result.stdout
        assert 'Application diagnostics initialized' in result.stderr
        assert (tmp_path/'data').read_text() == 'existing file'
    assert not (tmp_path/'config').exists()
