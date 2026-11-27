# SPDX-License-Identifier: MIT
"""Read load and device-wide VRAM for the NVIDIA adapter used by CUDA OCR."""

import ctypes
from pathlib import Path
import time
import winreg


class Utilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class Memory(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in ("total", "free", "used")]


def _cuda_bus_id():
    cuda = ctypes.WinDLL("nvcuda.dll", winmode=0x800)
    cuda.cuInit.argtypes = [ctypes.c_uint]
    cuda.cuDeviceGet.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int]
    cuda.cuDeviceGetPCIBusId.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    ordinal = ctypes.c_int()
    bus = ctypes.create_string_buffer(32)
    if (cuda.cuInit(0) == 0 and cuda.cuDeviceGet(ctypes.byref(ordinal), 0) == 0
            and cuda.cuDeviceGetPCIBusId(bus, len(bus), ordinal.value) == 0):
        return bus.value
    return None


def _load_nvml():
    try:
        return ctypes.CDLL("nvml.dll", winmode=0x800)
    except OSError:
        key = r"SOFTWARE\Microsoft\Windows\CurrentVersion"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as item:
            directory, _ = winreg.QueryValueEx(item, "ProgramFilesDir")
        library = Path(directory) / "NVIDIA Corporation" / "NVSMI" / "nvml.dll"
        return ctypes.CDLL(str(library), winmode=0x900)


class NvidiaSampler:
    """Initialize once and keep driver calls on the telemetry worker."""

    def __init__(self):
        self.library = None
        self.device = ctypes.c_void_p()
        self.retry_at = 0.0

    def _open(self):
        library = _load_nvml()
        library.nvmlInit_v2.argtypes = []
        library.nvmlShutdown.argtypes = []
        library.nvmlDeviceGetHandleByPciBusId_v2.argtypes = [
            ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        library.nvmlDeviceGetCount_v2.argtypes = [ctypes.POINTER(ctypes.c_uint)]
        library.nvmlDeviceGetHandleByIndex_v2.argtypes = [
            ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
        library.nvmlDeviceGetUtilizationRates.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(Utilization)]
        library.nvmlDeviceGetMemoryInfo.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(Memory)]
        if library.nvmlInit_v2() != 0:
            return False
        self.library = library
        try:
            bus = _cuda_bus_id()
        except (OSError, AttributeError):
            bus = None
        if bus and library.nvmlDeviceGetHandleByPciBusId_v2(bus, ctypes.byref(self.device)) == 0:
            return True
        count = ctypes.c_uint()
        if (not bus and library.nvmlDeviceGetCount_v2(ctypes.byref(count)) == 0 and count.value == 1
                and library.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self.device)) == 0):
            return True
        self.close()
        return False

    def sample(self, metric):
        if self.library is None:
            now = time.monotonic()
            if now < self.retry_at:
                return time.perf_counter(), None
            self.retry_at = now + 20
            try:
                if not self._open():
                    return time.perf_counter(), None
            except (OSError, AttributeError):
                self.close()
                return time.perf_counter(), None
        if metric == 0:
            usage = Utilization()
            status = self.library.nvmlDeviceGetUtilizationRates(self.device, ctypes.byref(usage))
            value = float(usage.gpu) if status == 0 and usage.gpu <= 100 else None
        else:
            memory = Memory()
            status = self.library.nvmlDeviceGetMemoryInfo(self.device, ctypes.byref(memory))
            value = memory.used / 1024**2 if status == 0 and memory.used <= memory.total else None
        if status == 15:  # NVML_ERROR_GPU_IS_LOST
            self.close()
        return time.perf_counter(), value

    def close(self):
        library, self.library = self.library, None
        self.device = ctypes.c_void_p()
        if library is not None:
            library.nvmlShutdown()
