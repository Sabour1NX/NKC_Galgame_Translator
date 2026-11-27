# SPDX-License-Identifier: MIT
"""Explicitly arm one non-forced shutdown after 60 seconds without user input.

This tool is never armed on import or by the translation application. Run it
only after the development/report task is complete, with ``--arm``. Creating
the stop file (or running ``--cancel``) cancels the pending watcher. The stop
file is intentionally retained, so a cancelled watcher cannot silently rearm.

``--dry-run`` never invokes shutdown. Only dry runs may use an idle threshold
shorter than 60 seconds. Tests inject snapshots, sleep and a harmless action.

GetLastInputInfo describes the current Windows login session, not all RDP
sessions. Shutdown uses /s /t 0 without /f: applications may block shutdown.
Microsoft documents that /t greater than zero implicitly enables /f, which
is why all waiting is done here and no OS shutdown countdown is scheduled.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STOP_FILE = ROOT / 'data' / 'idle_shutdown.stop'
DEFAULT_LOG_FILE = ROOT / 'artifacts' / 'idle_shutdown.jsonl'
DWORD_MASK = (1 << 32) - 1


@dataclass(frozen=True)
class InputSnapshot:
    tick_ms: int
    last_input_tick: int


def idle_age_ms(snapshot: InputSnapshot) -> int:
    """Map LASTINPUTINFO's DWORD into GetTickCount64's current wrap interval."""
    return (int(snapshot.tick_ms) - int(snapshot.last_input_tick)) & DWORD_MASK


class IdleGate:
    """Require an entire quiet interval after arming and each observed input."""
    def __init__(self, initial: InputSnapshot, required_ms: int = 60_000):
        if required_ms <= 0:
            raise ValueError('Idle interval must be positive.')
        self.required_ms = required_ms
        self.armed_ms = self.quiet_since_ms = self.previous_ms = initial.tick_ms
        self.last_input_tick = initial.last_input_tick

    def observe(self, snapshot: InputSnapshot) -> bool:
        now = snapshot.tick_ms
        if now < self.previous_ms:
            # Fail closed if a synthetic/replaced clock goes backwards.
            self.armed_ms = self.quiet_since_ms = now
        elif snapshot.last_input_tick != self.last_input_tick:
            # Windows does not guarantee last-input ticks always increase.
            # Any changed value is activity, even a backdated SendInput event.
            self.quiet_since_ms = now
        elif now - self.previous_ms > 5_000:
            # A resumed/suspended or stalled watcher must observe a fresh quiet
            # interval before acting; time asleep cannot immediately shut down.
            self.quiet_since_ms = now
        self.last_input_tick = snapshot.last_input_tick
        self.previous_ms = now
        return min(now - self.armed_ms, now - self.quiet_since_ms,
                   idle_age_ms(snapshot)) >= self.required_ms


class _LastInputInfo(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]


class WindowsInputClock:
    def __init__(self):
        if sys.platform != 'win32':
            raise RuntimeError('Idle shutdown is available only on Windows.')
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LastInputInfo)]
        self.user32.GetLastInputInfo.restype = wintypes.BOOL
        self.kernel32.GetTickCount64.argtypes = []
        self.kernel32.GetTickCount64.restype = ctypes.c_ulonglong

    def __call__(self) -> InputSnapshot:
        info = _LastInputInfo()
        info.cbSize = ctypes.sizeof(info)
        if not self.user32.GetLastInputInfo(ctypes.byref(info)):
            raise RuntimeError('Unable to read Windows input idle state.')
        return InputSnapshot(int(self.kernel32.GetTickCount64()), int(info.dwTime))


class JsonEventLog:
    """A fixed event schema: no exception messages, environment or config data."""
    EVENTS = {'armed', 'cancelled', 'dry_run_ready', 'shutdown_requested',
              'shutdown_result', 'failed'}
    FIELDS = {'dry_run', 'idle_seconds', 'idle_ms', 'elapsed_ms', 'return_code'}

    def __init__(self, path: Path):
        self.path = Path(path)

    def __call__(self, event: str, **fields) -> None:
        if event not in self.EVENTS:
            raise ValueError('Unsupported idle watcher event.')
        record = {'time': datetime.now(timezone.utc).isoformat(), 'event': event}
        record.update({name: value for name, value in fields.items()
                       if name in self.FIELDS and isinstance(value, (bool, int, float))
                       and (not isinstance(value, float) or math.isfinite(value))})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + '\n')
            handle.flush()


def _system_shutdown_path() -> str:
    if sys.platform != 'win32':
        raise RuntimeError('Shutdown is available only on Windows.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetSystemDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    kernel.GetSystemDirectoryW.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise RuntimeError('Unable to locate the Windows system directory.')
    return str(Path(buffer.value) / 'shutdown.exe')


def request_shutdown() -> int:
    """Request once, with no shell, window, forced closure, or OS countdown."""
    result = subprocess.run([_system_shutdown_path(), '/s', '/t', '0'],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, check=False, timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    return result.returncode


def run_once(snapshot: Callable[[], InputSnapshot], *,
             stop_requested: Callable[[], bool], emit: Callable,
             idle_seconds: float = 60.0, poll_seconds: float = 0.5,
             dry_run: bool = True, sleep: Callable = time.sleep,
             shutdown_action: Callable[[], int] = request_shutdown) -> str:
    """Observe once until cancellation/readiness; injected dependencies aid tests."""
    if not math.isfinite(idle_seconds) or idle_seconds <= 0:
        raise ValueError('Idle interval must be a finite positive number.')
    if not dry_run and idle_seconds < 60:
        raise ValueError('Real shutdown requires at least 60 idle seconds.')
    if not math.isfinite(poll_seconds) or not 0 < poll_seconds <= 5:
        raise ValueError('Polling interval must be between zero and five seconds.')
    if stop_requested():
        emit('cancelled', dry_run=dry_run)
        return 'cancelled'
    initial = snapshot()
    gate = IdleGate(initial, math.ceil(idle_seconds * 1000))
    emit('armed', dry_run=dry_run, idle_seconds=idle_seconds)
    while True:
        if stop_requested():
            emit('cancelled', dry_run=dry_run)
            return 'cancelled'
        current = snapshot()
        if gate.observe(current):
            # Close the polling gap: activity at the deadline starts a new full
            # interval, and cancellation is checked again immediately before use.
            current = snapshot()
            ready = gate.observe(current)
            if stop_requested():
                emit('cancelled', dry_run=dry_run)
                return 'cancelled'
            if ready:
                fields = {'dry_run': dry_run, 'idle_ms': idle_age_ms(current),
                          'elapsed_ms': current.tick_ms - gate.armed_ms}
                if dry_run:
                    emit('dry_run_ready', **fields)
                    return 'dry_run'
                emit('shutdown_requested', **fields)
                result = int(shutdown_action())
                emit('shutdown_result', return_code=result)
                return 'requested' if result == 0 else 'failed'
        sleep(poll_seconds)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', action='store_true', help='Explicitly arm the one-time shutdown watcher.')
    parser.add_argument('--dry-run', action='store_true', help='Observe readiness and log it; never shut down.')
    parser.add_argument('--cancel', action='store_true', help='Create the stop file and exit without arming.')
    parser.add_argument('--idle-seconds', type=float, default=60.0)
    parser.add_argument('--poll-seconds', type=float, default=0.5)
    parser.add_argument('--stop-file', type=Path, default=DEFAULT_STOP_FILE)
    parser.add_argument('--log-file', type=Path, default=DEFAULT_LOG_FILE)
    args = parser.parse_args(argv)
    if not (args.arm or args.dry_run or args.cancel):
        parser.error('Choose --arm, --dry-run, or --cancel; nothing is armed by default.')
    if args.cancel:
        args.stop_file.parent.mkdir(parents=True, exist_ok=True)
        args.stop_file.write_text('cancel\n', encoding='ascii')
        return 0
    if not args.dry_run and args.idle_seconds < 60:
        parser.error('Intervals shorter than 60 seconds require --dry-run.')
    log = JsonEventLog(args.log_file)
    try:
        if args.stop_file.exists():
            log('cancelled', dry_run=args.dry_run)
            return 0
        result = run_once(WindowsInputClock(), stop_requested=args.stop_file.exists,
                          emit=log, idle_seconds=args.idle_seconds,
                          poll_seconds=args.poll_seconds, dry_run=args.dry_run)
        return 0 if result != 'failed' else 1
    except (Exception, KeyboardInterrupt):
        # No raw system error text or arguments enter the log or console.
        try:
            log('failed', dry_run=args.dry_run)
        except Exception:
            pass
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
