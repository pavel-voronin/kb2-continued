"""Locations and CPU limits for the Pascal test host."""

import os, tempfile
from pathlib import Path


def limit_host_cpu():
    """Share two logical processors across this stand and its child processes."""
    if os.name == "nt":
        import ctypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.GetProcessAffinityMask.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t),
        ]
        kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        process = kernel.GetCurrentProcess()
        available, system = ctypes.c_size_t(), ctypes.c_size_t()
        if not kernel.GetProcessAffinityMask(
            process, ctypes.byref(available), ctypes.byref(system)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        mask = available.value
        first = mask & -mask
        rest = mask & ~first
        selected = first | (rest & -rest)
        if not kernel.SetProcessAffinityMask(process, selected):
            raise ctypes.WinError(ctypes.get_last_error())
        kernel.SetPriorityClass(process, 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS


limit_host_cpu()

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORK = (
    ROOT / ".git/kb2-test"
    if (ROOT / ".git").is_dir()
    else Path(tempfile.gettempdir()) / "kb2-test"
)
WORK = Path(os.environ.get("KB2_TEST_WORK", str(DEFAULT_WORK))).resolve()
