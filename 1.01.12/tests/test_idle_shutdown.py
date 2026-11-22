# SPDX-License-Identifier: MIT
"""Pure fake-clock shutdown policy tests. No test invokes Windows shutdown."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'idle_shutdown.py'
SPEC = importlib.util.spec_from_file_location('idle_shutdown_under_test', SCRIPT)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class FakeClock:
    def __init__(self, now=300_000, last_input=0, events=None):
        self.now = now
        self.last_input = last_input & module.DWORD_MASK
        self.events = dict(events or {})

    def __call__(self):
        return module.InputSnapshot(self.now, self.last_input)

    def sleep(self, seconds):
        self.now += round(seconds * 1000)
        for when in sorted(list(self.events)):
            if self.now >= when:
                self.last_input = self.events.pop(when) & module.DWORD_MASK


def watch(clock, **options):
    action = options.pop('shutdown_action', Mock(return_value=0))
    log = Mock()
    result = module.run_once(clock, stop_requested=options.pop('stop_requested', lambda: False),
                             emit=log, sleep=clock.sleep, shutdown_action=action, **options)
    return result, log, action


def test_import_does_not_launch_or_arm_anything(monkeypatch):
    process = Mock(side_effect=AssertionError('Import must not launch a process'))
    monkeypatch.setattr(subprocess, 'run', process)
    another_spec = importlib.util.spec_from_file_location('idle_shutdown_import_only', SCRIPT)
    another = importlib.util.module_from_spec(another_spec)
    sys.modules[another_spec.name] = another
    another_spec.loader.exec_module(another)
    process.assert_not_called()


@pytest.mark.parametrize('now,last_tick,expected', [
    (100_000, 40_000, 60_000),
    ((1 << 32) + 40_000, (1 << 32) - 20_000, 60_000),
    (3 * (1 << 32) + 40_000, (1 << 32) - 20_000, 60_000),
    ((1 << 32) + 1, (1 << 32) - 1, 2),
])
def test_last_input_dword_age_is_wrap_safe(now, last_tick, expected):
    assert module.idle_age_ms(module.InputSnapshot(now, last_tick)) == expected


def test_already_idle_at_arming_still_waits_a_complete_sixty_seconds():
    clock = FakeClock()
    armed = clock.now
    result, log, action = watch(clock, dry_run=False)
    assert result == 'requested'
    assert clock.now - armed == 60_000
    action.assert_called_once_with()
    assert [call.args[0] for call in log.call_args_list] == [
        'armed', 'shutdown_requested', 'shutdown_result']


def test_observed_keyboard_or_mouse_input_resets_full_interval():
    # Every GetLastInputInfo change represents activity, regardless of device.
    clock = FakeClock(events={359_000: 359_000, 418_000: 418_000})
    result, _, action = watch(clock, dry_run=False)
    assert result == 'requested'
    assert clock.now == 478_000
    action.assert_called_once()


def test_backdated_input_tick_also_resets_full_interval():
    clock = FakeClock(last_input=100, events={359_000: 10})
    result, _, action = watch(clock, dry_run=False)
    assert result == 'requested'
    assert clock.now == 419_000
    action.assert_called_once()


def test_arming_and_idle_timer_survive_uptime_dword_wrap():
    clock = FakeClock(now=(1 << 32) - 30_000, last_input=(1 << 32) - 120_000)
    initial = clock.now
    result, _, action = watch(clock, dry_run=False)
    assert result == 'requested'
    assert clock.now - initial == 60_000
    assert clock.now > 1 << 32
    action.assert_called_once()


def test_input_arriving_during_final_read_prevents_shutdown():
    clock = FakeClock()
    armed = clock.now
    reads_at_deadline = 0
    def final_input():
        nonlocal reads_at_deadline
        if clock.now == armed + 60_000:
            reads_at_deadline += 1
            if reads_at_deadline == 2:
                clock.last_input = clock.now & module.DWORD_MASK
        return clock()
    action = Mock(return_value=0)
    result = module.run_once(final_input, stop_requested=lambda: False,
                             emit=Mock(), sleep=clock.sleep, dry_run=False,
                             shutdown_action=action)
    assert result == 'requested'
    assert clock.now == armed + 120_000
    action.assert_called_once()


def test_stop_file_presence_cancels_before_clock_or_action(tmp_path):
    stop_file = tmp_path / 'idle_shutdown.stop'
    stop_file.write_text('cancel')
    clock, action, log = Mock(), Mock(), Mock()
    result = module.run_once(clock, stop_requested=stop_file.exists,
                             emit=log, dry_run=False, shutdown_action=action)
    assert result == 'cancelled'
    clock.assert_not_called()
    action.assert_not_called()
    assert stop_file.exists()


def test_stop_file_created_while_waiting_cancels_pending_watch(tmp_path):
    stop_file = tmp_path / 'idle_shutdown.stop'
    clock = FakeClock()
    def sleep(seconds):
        clock.sleep(seconds)
        if clock.now >= 330_000:
            stop_file.write_text('cancel')
    action = Mock()
    result = module.run_once(clock, stop_requested=stop_file.exists, emit=Mock(),
                             sleep=sleep, dry_run=False, shutdown_action=action)
    assert result == 'cancelled'
    assert clock.now == 330_000
    action.assert_not_called()


def test_cancel_at_last_pre_action_check_prevents_command():
    clock = FakeClock()
    armed, deadline_reads, cancelled = clock.now, 0, False
    def final_snapshot():
        nonlocal deadline_reads, cancelled
        if clock.now == armed + 60_000:
            deadline_reads += 1
            if deadline_reads == 2:
                cancelled = True
        return clock()
    action = Mock()
    result = module.run_once(final_snapshot, stop_requested=lambda: cancelled,
                             emit=Mock(), sleep=clock.sleep, dry_run=False,
                             shutdown_action=action)
    assert result == 'cancelled'
    action.assert_not_called()


def test_dry_run_reaches_ready_without_calling_shutdown():
    clock = FakeClock()
    result, log, action = watch(clock, dry_run=True, idle_seconds=0.1, poll_seconds=0.05)
    assert result == 'dry_run'
    assert clock.now == 300_100
    action.assert_not_called()
    assert log.call_args.args[0] == 'dry_run_ready'


@pytest.mark.parametrize('threshold', [0.1, 59.999, 0, -1, float('nan'), float('inf')])
def test_real_mode_cannot_use_short_or_invalid_intervals(threshold):
    action = Mock()
    with pytest.raises(ValueError):
        module.run_once(Mock(), stop_requested=lambda: False, emit=Mock(),
                        idle_seconds=threshold, dry_run=False, shutdown_action=action)
    action.assert_not_called()


@pytest.mark.parametrize('interval', [0, -1, 5.01, float('nan'), float('inf')])
def test_invalid_poll_interval_cannot_arm(interval):
    source, action = Mock(), Mock()
    with pytest.raises(ValueError):
        module.run_once(source, stop_requested=lambda: False, emit=Mock(),
                        poll_seconds=interval, dry_run=False, shutdown_action=action)
    source.assert_not_called()
    action.assert_not_called()


def test_long_watcher_stall_requires_fresh_observed_idle_interval():
    gate = module.IdleGate(module.InputSnapshot(100_000, 0))
    assert not gate.observe(module.InputSnapshot(200_000, 0))
    for now in range(201_000, 260_000, 1000):
        assert not gate.observe(module.InputSnapshot(now, 0))
    assert gate.observe(module.InputSnapshot(260_000, 0))


def test_backwards_clock_rearms_instead_of_shutting_down():
    gate = module.IdleGate(module.InputSnapshot(100_000, 0))
    assert not gate.observe(module.InputSnapshot(50_000, 0))
    for now in range(51_000, 110_000, 1000):
        assert not gate.observe(module.InputSnapshot(now, 0))
    assert gate.observe(module.InputSnapshot(110_000, 0))


def test_nonzero_shutdown_status_is_reported_once_without_retry():
    action = Mock(return_value=5)
    result, log, _ = watch(FakeClock(), dry_run=False, shutdown_action=action)
    assert result == 'failed'
    action.assert_called_once()
    assert log.call_args.kwargs == {'return_code': 5}


def test_request_command_is_hidden_nonforced_and_has_zero_os_timeout(monkeypatch):
    process = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(module, '_system_shutdown_path', lambda: 'C:/Windows/System32/shutdown.exe')
    monkeypatch.setattr(module.subprocess, 'run', process)
    assert module.request_shutdown() == 0
    args, options = process.call_args
    assert args == (['C:/Windows/System32/shutdown.exe', '/s', '/t', '0'],)
    assert options['creationflags'] == subprocess.CREATE_NO_WINDOW
    assert options['stdin'] == options['stdout'] == options['stderr'] == subprocess.DEVNULL
    assert not options.get('shell', False)
    assert '/f' not in args[0] and '/p' not in args[0]


def test_log_schema_excludes_strings_paths_exception_text_and_nonfinite(tmp_path):
    secret = 'synthetic-private-value-that-must-not-enter-logs'
    path = tmp_path / 'events.jsonl'
    module.JsonEventLog(path)('armed', dry_run=True, idle_seconds=60,
                             error=secret, api_key=secret, path=secret,
                             elapsed_ms=secret, idle_ms=float('nan'))
    content = path.read_text(encoding='utf-8')
    assert secret not in content
    record = json.loads(content)
    assert set(record) == {'time', 'event', 'dry_run', 'idle_seconds'}
    assert record['event'] == 'armed'


def test_cli_requires_explicit_arm_or_dry_run(monkeypatch):
    clock = Mock(side_effect=AssertionError('Should not initialize clock'))
    monkeypatch.setattr(module, 'WindowsInputClock', clock)
    with pytest.raises(SystemExit) as error:
        module.main([])
    assert error.value.code == 2
    clock.assert_not_called()


def test_cli_short_real_threshold_is_refused_before_windows_calls(monkeypatch):
    clock = Mock(side_effect=AssertionError('Should not initialize clock'))
    monkeypatch.setattr(module, 'WindowsInputClock', clock)
    with pytest.raises(SystemExit) as error:
        module.main(['--arm', '--idle-seconds', '0.1'])
    assert error.value.code == 2
    clock.assert_not_called()


def test_cli_cancel_only_creates_stopfile_and_never_arms(tmp_path, monkeypatch):
    clock = Mock(side_effect=AssertionError('Cancellation must not read Windows idle state'))
    monkeypatch.setattr(module, 'WindowsInputClock', clock)
    stop_file = tmp_path / 'stop'
    assert module.main(['--cancel', '--stop-file', str(stop_file)]) == 0
    assert stop_file.read_text(encoding='ascii') == 'cancel\n'
    clock.assert_not_called()


def test_cli_catches_sensitive_exception_without_logging_its_message(tmp_path, monkeypatch):
    secret = 'synthetic-private-value-not-for-logs'
    monkeypatch.setattr(module, 'WindowsInputClock', Mock(side_effect=RuntimeError(secret)))
    log, stop = tmp_path / 'events.jsonl', tmp_path / 'stop'
    assert module.main(['--dry-run', '--log-file', str(log), '--stop-file', str(stop)]) == 1
    content = log.read_text(encoding='utf-8')
    assert secret not in content
    assert json.loads(content)['event'] == 'failed'


def test_cli_dry_run_short_interval_with_synthetic_clock_never_runs_subprocess(tmp_path, monkeypatch):
    clock = FakeClock()
    def advancing_clock():
        clock.now += 1
        return clock()
    monkeypatch.setattr(module, 'WindowsInputClock', lambda: advancing_clock)
    process = Mock(side_effect=AssertionError('Dry run must never launch shutdown'))
    monkeypatch.setattr(module.subprocess, 'run', process)
    log, stop = tmp_path / 'events.jsonl', tmp_path / 'stop'
    assert module.main(['--dry-run', '--idle-seconds', '0.001',
                        '--log-file', str(log), '--stop-file', str(stop)]) == 0
    process.assert_not_called()
    records = [json.loads(row) for row in log.read_text(encoding='utf-8').splitlines()]
    assert [record['event'] for record in records] == ['armed', 'dry_run_ready']
