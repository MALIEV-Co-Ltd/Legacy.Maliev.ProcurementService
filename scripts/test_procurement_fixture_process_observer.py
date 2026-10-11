"""Fake handles and subprocesses only; never launch native tests or Docker."""
import importlib.util
import errno
import pathlib
import signal
import tempfile
import unittest
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location("observer", pathlib.Path(__file__).with_name("observe-procurement-fixture-process.py"))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)

IDENTITY = {"pid": 17, "startTicks": 123, "group": 17, "session": 17, "executable": "/dotnet"}


class FakeHandle:
    def __init__(self, identity): self.identity, self.fd = identity, identity["pid"]
    def exited(self): return True
    def send(self, signum): raise AssertionError("Fake exited handle must never be signaled")
    def close(self): pass


def flattened(error):
    if isinstance(error, BaseExceptionGroup):
        return [value for child in error.exceptions for value in flattened(child)]
    return [error]


class ObserverControls(unittest.TestCase):
    def setUp(self): observer.phase_deadline = observer.time.monotonic() + 30

    def test_almost_expired_real_gate_path_refuses_before_popen(self):
        observer.phase_deadline = observer.time.monotonic() + 0.01
        with patch.object(observer.subprocess, "Popen") as spawn, patch.object(observer.os, "pipe") as pipe, patch.object(observer, "preflight_pidfd") as preflight:
            with self.assertRaises(TimeoutError): observer.spawn_gated(["docker"])
            spawn.assert_not_called(); pipe.assert_not_called(); preflight.assert_not_called()

    def test_acquisition_refusal_wait_is_clipped_and_unsettled_error_retained(self):
        primary = IOError("Acquisition refused"); child = MagicMock(pid=17)
        timeout = observer.subprocess.TimeoutExpired("holding gate", 0.5); child.wait.side_effect = timeout
        observer.phase_deadline = 10
        ticks = iter([0, 0, 0, 9.5])
        with patch.object(observer.time, "monotonic", side_effect=lambda: next(ticks, 9.5)), patch.object(observer, "preflight_pidfd"), patch.object(observer.shutil, "which", return_value="/dotnet"), patch.object(observer.os, "pipe", return_value=(31,32)), patch.object(observer.os, "close"), patch.object(observer.subprocess, "Popen", return_value=child), patch.object(observer, "process_identity", side_effect=primary):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.spawn_gated(["dotnet"])
            self.assertIn(primary, flattened(caught.exception)); self.assertIn(timeout, flattened(caught.exception))
            child.wait.assert_called_once_with(timeout=0.5)

    def test_acquisition_refusal_closes_every_stream_and_retains_all_faults(self):
        primary = IOError("Synthetic acquisition refusal")
        close_errors = [OSError("stdin close"), OSError("stdout close"), OSError("stderr close")]
        child = MagicMock(pid=17); child.wait.return_value = 125
        for stream, error in zip((child.stdin, child.stdout, child.stderr), close_errors): stream.close.side_effect = error
        with patch.object(observer, "preflight_pidfd"), patch.object(observer.shutil, "which", return_value="/dotnet"), patch.object(observer.os, "pipe", return_value=(31, 32)), patch.object(observer.os, "close"), patch.object(observer.os, "write") as admission, patch.object(observer.subprocess, "Popen", return_value=child), patch.object(observer, "process_identity", return_value=IDENTITY), patch.object(observer, "OwnedHandle", side_effect=primary):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.spawn_gated(["dotnet"], stdin=observer.subprocess.PIPE, stdout=observer.subprocess.PIPE, stderr=observer.subprocess.PIPE)
            self.assertEqual([primary, *close_errors], flattened(caught.exception)); admission.assert_not_called()
            for stream in (child.stdin, child.stdout, child.stderr): stream.close.assert_called_once()

    def test_record_keeps_launch_custody_and_requires_authorized_same_birth_exec(self):
        launch = dict(IDENTITY, executable="/python3")
        processes = {launch["pid"]: launch}
        observer.record_process(processes, IDENTITY, launch, "/dotnet")
        self.assertEqual("/python3", launch["executable"])
        self.assertEqual(IDENTITY, observer.process_custody(launch, "/dotnet", [launch, *processes.values()])["testProcess"])
        for field in ("startTicks", "group", "session", "executable"):
            changed = dict(IDENTITY); changed[field] = "/foreign" if field == "executable" else changed[field] + 1
            with self.subTest(field=field), self.assertRaises(RuntimeError): observer.record_process(processes, changed, launch, "/dotnet")

    def test_post_open_identity_exception_closes_descriptor(self):
        primary = IOError("Synthetic identity failure")
        with patch.object(observer.os, "pidfd_open", return_value=41, create=True), patch.object(observer.os, "close") as close, patch.object(observer, "process_identity", side_effect=primary):
            with self.assertRaises(IOError) as caught: observer.OwnedHandle(IDENTITY)
            self.assertIs(primary, caught.exception); close.assert_called_once_with(41)

    def test_post_open_identity_and_close_errors_both_survive(self):
        primary, cleanup = IOError("Synthetic identity failure"), OSError("Synthetic close failure")
        with patch.object(observer.os, "pidfd_open", return_value=41, create=True), patch.object(observer.os, "close", side_effect=cleanup), patch.object(observer, "process_identity", side_effect=primary):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.OwnedHandle(IDENTITY)
            self.assertEqual([primary, cleanup], list(caught.exception.exceptions))

    def test_owned_first_foreign_second_census_sample_refuses_handle(self):
        owned = dict(IDENTITY, pid=18, startTicks=124)
        foreign = dict(owned, group=99, session=99, startTicks=999, executable="/foreign")
        with patch.object(observer.pathlib.Path, "iterdir", return_value=[pathlib.Path("18")]), patch.object(observer, "process_identity", side_effect=[IDENTITY, owned, foreign]), patch.object(observer, "OwnedHandle") as handles:
            with self.assertRaises(RuntimeError): observer.terminal_census(IDENTITY)
            handles.assert_not_called()

    def test_kernel_enosys_or_permission_failure_prevents_popen(self):
        for code in (errno.ENOSYS, errno.EACCES):
            with patch.object(observer.os, "pidfd_open", side_effect=OSError(code, "Synthetic preflight refusal"), create=True), patch.object(observer.subprocess, "Popen") as spawn:
                with self.subTest(code=code), self.assertRaises(OSError): observer.spawn_gated(["dotnet"])
                spawn.assert_not_called()

    def test_preflight_checks_actual_signal_permission_and_closes_self_handle(self):
        with patch.object(observer.os, "getpid", return_value=17), patch.object(observer.os, "pidfd_open", return_value=41, create=True) as opened, patch.object(observer.signal, "pidfd_send_signal", create=True) as send, patch.object(observer.os, "close") as close:
            observer.preflight_pidfd()
            opened.assert_called_once_with(17); send.assert_called_once_with(41, 0); close.assert_called_once_with(41)

    def test_signal_permission_refusal_closes_handle_before_any_child(self):
        refusal = PermissionError(errno.EACCES, "Synthetic signal permission refusal")
        with patch.object(observer.os, "pidfd_open", return_value=41, create=True), patch.object(observer.signal, "pidfd_send_signal", side_effect=refusal, create=True), patch.object(observer.os, "close") as close, patch.object(observer.subprocess, "Popen") as spawn:
            with self.assertRaises(PermissionError) as caught: observer.spawn_gated(["dotnet"])
            self.assertIs(refusal, caught.exception); close.assert_called_once_with(41); spawn.assert_not_called()

    def test_preflight_signal_and_close_failures_both_survive_before_child(self):
        primary, cleanup = PermissionError("Synthetic permission refusal"), OSError("Synthetic preflight close failure")
        with patch.object(observer.os, "pidfd_open", return_value=41, create=True), patch.object(observer.signal, "pidfd_send_signal", side_effect=primary, create=True), patch.object(observer.os, "close", side_effect=cleanup), patch.object(observer.subprocess, "Popen") as spawn:
            with self.assertRaises(BaseExceptionGroup) as caught: observer.spawn_gated(["dotnet"])
            self.assertEqual([primary, cleanup], list(caught.exception.exceptions)); spawn.assert_not_called()

    def test_postspawn_acquisition_gap_never_releases_native_exec_gate(self):
        failure = IOError("Synthetic acquisition failure"); child = MagicMock(pid=17); child.wait.return_value = 125
        with patch.object(observer, "preflight_pidfd"), patch.object(observer.shutil, "which", return_value="/dotnet"), patch.object(observer.os, "pipe", return_value=(31, 32)), patch.object(observer.os, "close") as close, patch.object(observer.os, "write") as admission, patch.object(observer.subprocess, "Popen", return_value=child), patch.object(observer, "process_identity", return_value=IDENTITY), patch.object(observer, "OwnedHandle", side_effect=failure):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.spawn_gated(["dotnet", "test"])
            self.assertIn(failure, flattened(caught.exception)); admission.assert_not_called()
            self.assertEqual([((31,), {}), ((32,), {})], close.call_args_list)
            child.wait.assert_called_once()
            self.assertLessEqual(child.wait.call_args.kwargs["timeout"], 6)

    def test_pid_reuse_refuses_signal_even_with_a_retained_handle(self):
        with patch.object(observer.os, "pidfd_open", return_value=41, create=True), patch.object(observer.os, "close"), patch.object(observer, "process_identity", side_effect=[IDENTITY, dict(IDENTITY, startTicks=124)]), patch.object(observer.signal, "pidfd_send_signal", create=True) as send:
            handle = observer.OwnedHandle(IDENTITY)
            with self.assertRaises(RuntimeError): handle.send(signal.SIGTERM)
            send.assert_not_called(); handle.close()

    def test_verified_signal_uses_pidfd_not_numeric_pid(self):
        with patch.object(observer.os, "pidfd_open", return_value=41, create=True), patch.object(observer.os, "close"), patch.object(observer, "process_identity", return_value=IDENTITY), patch.object(observer.signal, "pidfd_send_signal", create=True) as send:
            handle = observer.OwnedHandle(IDENTITY); handle.send(signal.SIGTERM)
            send.assert_called_once_with(41, signal.SIGTERM); handle.close()

    def test_binding_birth_change_closes_handle_without_signaling(self):
        with patch.object(observer.os, "pidfd_open", return_value=41, create=True), patch.object(observer.os, "close") as close, patch.object(observer, "process_identity", return_value=dict(IDENTITY, startTicks=124)), patch.object(observer.signal, "pidfd_send_signal", create=True) as send:
            with self.assertRaises(RuntimeError): observer.OwnedHandle(IDENTITY)
            close.assert_called_once_with(41); send.assert_not_called()

    def test_terminal_census_includes_late_child_and_rejects_reused_session(self):
        late = dict(IDENTITY, pid=18, startTicks=124)
        with patch.object(observer.pathlib.Path, "iterdir", return_value=[pathlib.Path("17"), pathlib.Path("18")]), patch.object(observer, "process_identity", side_effect=lambda pid, executable=True: IDENTITY if pid == 17 else late):
            self.assertIn(late, observer.terminal_census(IDENTITY))
        with patch.object(observer, "process_identity", return_value=dict(IDENTITY, startTicks=999)):
            with self.assertRaises(RuntimeError): observer.terminal_census(IDENTITY)

    def test_docker_overflow_is_bounded_and_retains_primary(self):
        child = MagicMock(pid=17); child.wait.return_value = 0
        observer.phase_deadline = 100
        with patch.object(observer.time, "monotonic", return_value=0), patch.object(observer, "spawn_gated", return_value=(child, FakeHandle(IDENTITY), IDENTITY)), patch.object(observer, "preflight_pidfd"), patch.object(observer, "OwnedHandle", FakeHandle), patch.object(observer, "process_identity", return_value=IDENTITY), patch.object(observer.os, "set_blocking"), patch.object(observer.os, "read", return_value=b"x" * (observer.MAX_OUTPUT_BYTES + 1)):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.docker("ps")
            self.assertTrue(any(isinstance(error, BufferError) for error in flattened(caught.exception)))
            child.stdout.close.assert_called_once()

    def test_command_timeout_and_shared_budget_are_enforced(self):
        child = MagicMock(pid=17); child.wait.return_value = 0
        observer.phase_deadline = 100
        ticks = iter([0, 0, 11, 11])
        with patch.object(observer.time, "monotonic", side_effect=lambda: next(ticks, 11)), patch.object(observer, "spawn_gated", return_value=(child, FakeHandle(IDENTITY), IDENTITY)), patch.object(observer, "preflight_pidfd"), patch.object(observer, "OwnedHandle", FakeHandle), patch.object(observer, "process_identity", return_value=IDENTITY), patch.object(observer.os, "set_blocking"):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.docker("ps")
            self.assertTrue(any(isinstance(error, TimeoutError) for error in flattened(caught.exception)))
        observer.phase_deadline = 5
        with patch.object(observer.time, "monotonic", return_value=2): self.assertEqual(3, observer.remaining_timeout(10))
        with patch.object(observer.time, "monotonic", return_value=5):
            with self.assertRaises(TimeoutError): observer.remaining_timeout(10)

    def test_proc_byte_and_census_cardinality_limits_fail_closed(self):
        stream = MagicMock(); stream.__enter__.return_value.read.return_value = b"x" * (observer.MAX_PROC_BYTES + 1)
        with patch.object(observer.pathlib.Path, "open", return_value=stream):
            with self.assertRaises(BufferError): observer.process_identity(17)
        with patch.object(observer.pathlib.Path, "iterdir", return_value=[pathlib.Path(str(i)) for i in range(observer.MAX_PROCESSES + 1)]), patch.object(observer, "process_identity", return_value=None):
            with self.assertRaises(BufferError): observer.terminal_census(IDENTITY)

    def test_primary_poll_and_receipt_write_faults_are_all_retained(self):
        primary, poll_failure, write_failure = RuntimeError("primary"), IOError("poll"), OSError("receipt")
        child = MagicMock(pid=17); child.poll.side_effect = [primary, poll_failure]; child.wait.return_value = 0
        with tempfile.TemporaryDirectory() as directory, patch.object(observer.sys, "platform", "linux"), patch.object(observer.shutil, "which", return_value="/dotnet"), patch.object(observer.os.path, "realpath", side_effect=lambda path, **kwargs: str(path)), patch.object(observer.os, "pidfd_open", create=True), patch.object(observer.signal, "pidfd_send_signal", create=True), patch.object(observer, "spawn_gated", return_value=(child, FakeHandle(IDENTITY), IDENTITY)), patch.object(observer, "preflight_pidfd"), patch.object(observer, "OwnedHandle", FakeHandle), patch.object(observer, "process_identity", return_value=IDENTITY), patch.object(observer, "terminal_census", return_value=[]), patch.object(observer, "observe"), patch.object(observer, "docker", return_value=""), patch.object(observer.pathlib.Path, "write_text", side_effect=write_failure):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.run(pathlib.Path(directory))
            actual = flattened(caught.exception)
            for error in (primary, poll_failure, write_failure): self.assertIn(error, actual)

    def test_late_terminal_child_never_qualifies_cleanup(self):
        late = dict(IDENTITY, pid=18, startTicks=124)
        child = MagicMock(pid=17); child.poll.return_value = 0; child.wait.return_value = 0
        with tempfile.TemporaryDirectory() as directory, patch.object(observer.sys, "platform", "linux"), patch.object(observer.shutil, "which", return_value="/dotnet"), patch.object(observer.os.path, "realpath", side_effect=lambda path, **kwargs: str(path)), patch.object(observer.os, "pidfd_open", create=True), patch.object(observer.signal, "pidfd_send_signal", create=True), patch.object(observer, "spawn_gated", return_value=(child, FakeHandle(IDENTITY), IDENTITY)), patch.object(observer, "preflight_pidfd"), patch.object(observer, "OwnedHandle", FakeHandle), patch.object(observer, "process_identity", return_value=IDENTITY), patch.object(observer, "terminal_census", side_effect=[[late], []]), patch.object(observer, "observe"), patch.object(observer, "docker", return_value=""):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.run(pathlib.Path(directory))
            self.assertTrue(any("Late owned descendant" in str(error) for error in flattened(caught.exception)))


if __name__ == "__main__": unittest.main()
