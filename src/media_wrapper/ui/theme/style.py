"""Platform-independent fallback rendering and matching dialog icons."""
from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleFactory

from media_wrapper.ui.theme.icons import icon


class StudioStyle(QProxyStyle):
    def __init__(self) -> None:
        super().__init__(QStyleFactory.create('Fusion'))

    def standardIcon(self, standard_icon, option=None, widget=None):
        names = {
            QStyle.StandardPixmap.SP_DirIcon: 'folder',
            QStyle.StandardPixmap.SP_DirOpenIcon: 'folder',
            QStyle.StandardPixmap.SP_FileIcon: 'file',
            QStyle.StandardPixmap.SP_DirHomeIcon: 'folder',
            QStyle.StandardPixmap.SP_DirLinkIcon: 'folder',
            QStyle.StandardPixmap.SP_FileLinkIcon: 'file',
            QStyle.StandardPixmap.SP_ComputerIcon: 'media',
            QStyle.StandardPixmap.SP_DriveHDIcon: 'media',
            QStyle.StandardPixmap.SP_FileDialogNewFolder: 'plus',
            QStyle.StandardPixmap.SP_FileDialogToParent: 'import',
            QStyle.StandardPixmap.SP_FileDialogDetailedView: 'queue',
            QStyle.StandardPixmap.SP_FileDialogListView: 'queue',
            QStyle.StandardPixmap.SP_DialogOkButton: 'check',
            QStyle.StandardPixmap.SP_DialogCancelButton: 'close',
            QStyle.StandardPixmap.SP_DialogCloseButton: 'close',
            QStyle.StandardPixmap.SP_TitleBarCloseButton: 'close',
            QStyle.StandardPixmap.SP_TitleBarMinButton: 'minimize',
            QStyle.StandardPixmap.SP_TitleBarMaxButton: 'maximize',
            QStyle.StandardPixmap.SP_TitleBarNormalButton: 'restore',
            QStyle.StandardPixmap.SP_BrowserReload: 'refresh',
            QStyle.StandardPixmap.SP_ArrowDown: 'chevron-down',
            QStyle.StandardPixmap.SP_ArrowUp: 'chevron-up',
            QStyle.StandardPixmap.SP_ArrowLeft: 'chevron-left',
            QStyle.StandardPixmap.SP_ArrowRight: 'chevron-right',
            QStyle.StandardPixmap.SP_ArrowBack: 'chevron-left',
            QStyle.StandardPixmap.SP_ArrowForward: 'chevron-right',
            QStyle.StandardPixmap.SP_MediaPlay: 'play',
            QStyle.StandardPixmap.SP_MediaPause: 'pause',
        }
        if name := names.get(standard_icon):
            return icon(name)
        return super().standardIcon(standard_icon, option, widget)
