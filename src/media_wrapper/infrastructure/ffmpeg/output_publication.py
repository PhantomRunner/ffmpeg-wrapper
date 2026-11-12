"""Publish a verified adjacent temporary file without replacing any destination."""
import ctypes
import errno
import os
import sys
from pathlib import Path


def _linux_rename(temporary: Path, destination: Path) -> bool:
    """Support no-replace publication on mounts with no hard links, such as exFAT."""
    renameat2 = getattr(ctypes.CDLL(None, use_errno=True), 'renameat2', None)
    if renameat2 is None:
        return False
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    at_fdcwd, rename_noreplace = -100, 1
    if renameat2(at_fdcwd, os.fsencode(temporary), at_fdcwd, os.fsencode(destination), rename_noreplace) == 0:
        return True
    code = ctypes.get_errno()
    if code in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP}:
        return False
    raise OSError(code, os.strerror(code), destination)


def publish_output(temporary: Path, destination: Path) -> str:
    if os.name == 'nt':
        # On Windows os.rename explicitly refuses an existing destination.
        os.rename(temporary, destination)
        return ''
    if sys.platform == 'linux' and _linux_rename(temporary, destination):
        return ''
    os.link(temporary, destination)
    try:
        temporary.unlink()
    except OSError as error:
        return f'Output published; temporary link retained at {temporary}: {error}'
    return ''
