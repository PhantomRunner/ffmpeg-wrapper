"""Keep frozen Qt library search paths out of external FFmpeg processes."""
import os
import sys
from pathlib import Path


def external_environment() -> dict[str, str]:
    environment = dict(os.environ)
    if not getattr(sys, 'frozen', False):
        return environment
    if sys.platform.startswith('linux'):
        original = environment.get('LD_LIBRARY_PATH_ORIG')
        if original is None:
            environment.pop('LD_LIBRARY_PATH', None)
        else:
            environment['LD_LIBRARY_PATH'] = original
    if sys.platform == 'win32':
        root = Path(sys._MEIPASS).resolve()
        environment['PATH'] = os.pathsep.join(entry for entry in environment.get('PATH', '').split(os.pathsep)
                                              if entry and not Path(entry).resolve().is_relative_to(root))
    return environment


def initialize_external_processes() -> None:
    """Call after loading Qt in a frozen Windows app with no bundled helpers."""
    if getattr(sys, 'frozen', False) and sys.platform == 'win32':
        import ctypes
        if not ctypes.windll.kernel32.SetDllDirectoryW(None):
            raise OSError('Could not restore the Windows DLL search path for external processes')
