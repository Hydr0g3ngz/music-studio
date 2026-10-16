"""Keep newer Torch workers compatible with older Conda base interpreters."""

import os
from pathlib import Path

_HANDLES = []


def prepare_torch():
    if os.name != "nt" or _HANDLES:
        return
    import ctypes

    system = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(system, len(system))
    if not 0 < length < len(system):
        raise RuntimeError("Cannot locate the Windows C++ runtime")
    # Conda 3.12.4 carries 14.29 DLLs beside python.exe. Torch 2.10 failed in c10.dll
    # until the installed system 14.51 libraries were loaded first. Use absolute
    # system paths; do not change PATH, replace DLLs or patch the user's Conda.
    for name in ("msvcp140.dll", "msvcp140_atomic_wait.dll"):
        path = Path(system.value) / name
        if path.is_file():
            _HANDLES.append(ctypes.WinDLL(str(path), winmode=0x00001100))
