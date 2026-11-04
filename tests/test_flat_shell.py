from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMainWindow, QSplitter, QVBoxLayout, QWidget

from media_wrapper.domain.operations import MediaOperation
from media_wrapper.ui.shell import AppShell, WorkspaceLayout, WorkspaceToolbar
from media_wrapper.ui.theme import apply_theme


def test_contextual_toolbar_and_native_shell(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = QMainWindow()
    workspace = QWidget()
    toolbar = WorkspaceToolbar()
    QVBoxLayout(workspace).addWidget(toolbar)
    shell = AppShell(workspace, QWidget(), QWidget())
    window.setCentralWidget(shell)
    apply_theme(window)
    window.show()
    app.processEvents()
    assert toolbar.add_files.isVisible()
    for route in ('queue', 'settings'):
        shell.set_page(route)
        assert not toolbar.add_files.isVisible()
        assert shell.page == route
    shell.set_page('workspace')
    seen = []
    toolbar.operation_changed.connect(seen.append)
    toolbar.operation_buttons[MediaOperation.COMPRESS].click()
    assert seen == [MediaOperation.COMPRESS]
    assert len(shell.buttons) == 3
    window.close()


def test_splitter_roundtrip_and_legacy_routes(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / 'layout.ini'), QSettings.Format.IniFormat)
    split = QSplitter()
    split.addWidget(QWidget())
    split.addWidget(QWidget())
    split.resize(1000, 500)
    persistence = WorkspaceLayout(split, settings)
    persistence.restore()
    split.setSizes([600, 400])
    persistence.save()
    persistence.restore()
    assert all(size > 0 for size in split.sizes())
    assert WorkspaceLayout.legacy_route(4)[0] == 'queue'
    assert WorkspaceLayout.legacy_route(5)[0] == 'settings'
    assert WorkspaceLayout.legacy_route(3) == ('workspace', MediaOperation.COMPRESS)
    split.close()
    app.processEvents()
