"""Windows installer/uninstaller guard; never closes or pauses processing jobs."""
import ctypes
import sys

MUTEX_NAME = r'Local\MediaWrapper.FlatUI'


class InstallationGuard:
    def __init__(self):
        self.handle = None
        if sys.platform == 'win32':
            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
            self.kernel.CreateMutexW.restype = ctypes.c_void_p
            self.kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
            self.kernel.CloseHandle.restype = ctypes.c_int
            self.handle = self.kernel.CreateMutexW(None, False, MUTEX_NAME)
            if not self.handle:
                raise OSError(ctypes.get_last_error(), 'Could not create the installer guard')

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
