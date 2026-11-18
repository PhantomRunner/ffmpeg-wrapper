"""Launch media processes whose lifetime is tied to the application."""
import ctypes
import os
import signal
import sys
from pathlib import Path

_CHILD = '--media-wrapper-owned-child'


def owned_command(arguments: list[str]) -> list[str]:
    if not arguments or not (sys.platform.startswith('linux') or sys.platform == 'win32'):
        return arguments
    entry = [] if getattr(sys, 'frozen', False) else ['-I', '-S', str(Path(__file__).resolve())]
    identity = str(os.getpid())
    if sys.platform == 'win32':
        kernel = _windows_kernel()
        identity += ':' + str(_creation_time(kernel, kernel.GetCurrentProcess()))
    return [sys.executable, *entry, _CHILD, identity, *arguments]


def _linux_run(parent: str, arguments: list[str]) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    # Set the death signal first to cover the race with the parent already exiting.
    if libc.prctl(1, int(signal.SIGKILL), 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), 'Cannot attach the child to the application')
    if os.getppid() != int(parent):
        raise ProcessLookupError('The application exited before the media process started')
    os.execvp(arguments[0], arguments)


def _windows_kernel():
    from ctypes import wintypes

    dword, handle = wintypes.DWORD, wintypes.HANDLE
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    functions = {
        'GetCurrentProcess': (handle, ()),
        'OpenProcess': (handle, (dword, wintypes.BOOL, dword)),
        'GetProcessTimes': (wintypes.BOOL, (handle,) + (ctypes.POINTER(wintypes.FILETIME),) * 4),
        'CreateJobObjectW': (handle, (ctypes.c_void_p, ctypes.c_wchar_p)),
        'SetInformationJobObject': (wintypes.BOOL, (handle, ctypes.c_int, ctypes.c_void_p, dword)),
        'AssignProcessToJobObject': (wintypes.BOOL, (handle, handle)),
        'WaitForMultipleObjects': (dword, (dword, ctypes.POINTER(handle), wintypes.BOOL, dword)),
        'CloseHandle': (wintypes.BOOL, (handle,)),
    }
    for name, (result_type, argument_types) in functions.items():
        function = getattr(kernel, name)
        function.restype = result_type
        function.argtypes = argument_types
    return kernel


def _creation_time(kernel, process) -> int:
    from ctypes import wintypes

    stamps = tuple(wintypes.FILETIME() for _ in range(4))
    if not kernel.GetProcessTimes(process, *(ctypes.byref(stamp) for stamp in stamps)):
        raise ctypes.WinError(ctypes.get_last_error())
    return (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime


def _windows_job(kernel):
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64), ('flags', wintypes.DWORD),
            ('working_min', ctypes.c_size_t), ('working_max', ctypes.c_size_t), ('active', wintypes.DWORD),
            ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ('basic', BasicLimits), ('io_metrics', ctypes.c_uint64 * 6),
            ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
            ('process_peak', ctypes.c_size_t), ('job_peak', ctypes.c_size_t),
        ]

    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not (kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
            and kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess())):
        error = ctypes.get_last_error()
        kernel.CloseHandle(handle)
        raise ctypes.WinError(error)
    # The watchdog is part of its own job; its non-inheritable handle remains
    # open until exit, so even a forced watchdog termination reaps descendants.
    return handle


def _windows_run(parent: str, arguments: list[str]) -> int:
    import subprocess
    from ctypes import wintypes

    kernel = _windows_kernel()
    pid, created = (int(value) for value in parent.split(':'))
    parent_process = kernel.OpenProcess(0x101000, False, pid)  # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
    if not parent_process:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if _creation_time(kernel, parent_process) != created:
            raise ProcessLookupError('The application exited before the media process started')
        _windows_job(kernel)
        process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        child = kernel.OpenProcess(0x100000, False, process.pid)  # SYNCHRONIZE
        if not child:
            if process.poll() is not None:
                return process.returncode
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            wait_for = (wintypes.HANDLE * 2)(parent_process, child)
            result = kernel.WaitForMultipleObjects(2, wait_for, False, 0xFFFFFFFF)
        finally:
            kernel.CloseHandle(child)
        if result == 1:
            return process.wait()
        if result == 0:
            return 125  # Watchdog exits and its job is closed.
        raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(parent_process)


def child_entry(argv: list[str]) -> int | None:
    if len(argv) < 2 or argv[1] != _CHILD:
        return None
    if len(argv) < 4:
        return 125
    try:
        if getattr(sys, 'frozen', False):
            from media_wrapper.infrastructure.process_environment import (
                external_environment,
                initialize_external_processes,
            )
            initialize_external_processes()
            environment = external_environment()
            os.environ.clear()
            os.environ.update(environment)
        if sys.platform == 'win32':
            return _windows_run(argv[2], argv[3:])
        _linux_run(argv[2], argv[3:])
    except (OSError, ValueError) as error:
        message = f'Could not run the managed media process: {error}'
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        elif sys.platform == 'win32':
            import _winapi

            try:
                _winapi.WriteFile(_winapi.GetStdHandle(_winapi.STD_ERROR_HANDLE), (message + '\n').encode('utf-8'))
            except OSError:
                pass
        return 125
    return 125


if __name__ == '__main__':
    raise SystemExit(child_entry(sys.argv))
