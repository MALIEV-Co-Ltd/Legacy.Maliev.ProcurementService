"""Fake handles and subprocesses only; never launch native tests or Docker."""
import importlib.util
import json
import re
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
    def setUp(self):
        observer.phase_deadline = observer.time.monotonic() + 30
        # These existing fake-host lifecycle tests exercise cleanup, not host admission.
        memory = patch.object(observer, "require_native_memory")
        memory.start(); self.addCleanup(memory.stop)
        # Existing fake-host cleanup tests intentionally exercise the frozen old18 lane.
        declaration = patch.object(observer, "native_extension", return_value={"enabled": False})
        declaration.start(); self.addCleanup(declaration.stop)

    def test_query_primary_and_both_stream_close_errors_are_retained(self):
        child = MagicMock(pid=17); child.poll.return_value = 2; child.returncode = 2
        stdout_failure, stderr_failure = IOError("stdout close"), OSError("stderr close")
        child.stdout.close.side_effect = stdout_failure; child.stderr.close.side_effect = stderr_failure
        with patch.object(observer, "spawn_gated", return_value=(child, FakeHandle(IDENTITY), IDENTITY)), patch.object(observer.os, "set_blocking"), patch.object(observer.os, "read", return_value=b""):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.docker("inspect", "a" * 64)
            errors = flattened(caught.exception)
            self.assertIsInstance(errors[0], observer.DockerObservationFailure)
            self.assertIn(stdout_failure, errors); self.assertIn(stderr_failure, errors)
            self.assertFalse(observer.command_failure_custody([caught.exception])[0]["streamsClosed"])

    def test_stderr_byte_overflow_remains_failure_and_closes_both_streams(self):
        child = MagicMock(pid=17); child.stdout.fileno.return_value = 51; child.stderr.fileno.return_value = 52
        with patch.object(observer, "spawn_gated", return_value=(child, FakeHandle(IDENTITY), IDENTITY)), patch.object(observer.os, "set_blocking"), patch.object(observer.os, "read", side_effect=lambda fd, size: b"" if fd == 51 else b"x" * (observer.MAX_ERROR_BYTES + 1)):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.docker("inspect", "a" * 64)
            self.assertTrue(any(isinstance(error, BufferError) for error in flattened(caught.exception)))
            child.stdout.close.assert_called_once(); child.stderr.close.assert_called_once()

    def test_exact_query_failure_custody_is_bounded_and_privacy_safe(self):
        target = "a" * 64
        known = observer.DockerObservationFailure(("inspect", target), 1, ("Error: No such object: " + target + "\n").encode())
        self.assertEqual("exact-container-not-found", known.custody["category"])
        self.assertEqual(target, known.custody["containerId"])
        unknown = observer.DockerObservationFailure(("inspect", target), 2, b"private-customer-data")
        self.assertNotIn("private-customer-data", str(unknown.custody))
        self.assertEqual("unclassified-command-failure", unknown.custody["category"])
        self.assertEqual([known.custody, unknown.custody], observer.command_failure_custody([BaseExceptionGroup("original", [known, unknown])]))

    def test_failed_docker_query_captures_stderr_and_closes_both_streams(self):
        child = MagicMock(pid=17); child.poll.return_value = 1; child.returncode = 1
        child.stdout.fileno.return_value = 51; child.stderr.fileno.return_value = 52
        target = "a" * 64; reads = {51: [b"", b""], 52: [("Error: No such object: " + target + "\n").encode(), b""]}
        with patch.object(observer, "spawn_gated", return_value=(child, FakeHandle(IDENTITY), IDENTITY)), patch.object(observer.os, "set_blocking"), patch.object(observer.os, "read", side_effect=lambda fd, size: reads[fd].pop(0)):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.docker("inspect", target)
            custody = observer.command_failure_custody([caught.exception])
            self.assertEqual(1, len(custody)); self.assertEqual(target, custody[0]["containerId"]); self.assertEqual(1, custody[0]["exitCode"])
            self.assertEqual(IDENTITY, custody[0]["commandLaunchProcess"]); self.assertTrue(custody[0]["childTerminalObserved"]); self.assertTrue(custody[0]["streamsClosed"]); self.assertTrue(custody[0]["handleClosed"])
            child.stdout.close.assert_called_once(); child.stderr.close.assert_called_once()

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
        ticks = iter([0, 0, 0, 11, 11])
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

    def test_docker_failure_does_not_skip_final_late_child_census_or_handle_close(self):
        late = dict(IDENTITY, pid=18, startTicks=124)
        docker_failure = observer.DockerObservationFailure(("inspect", "a" * 64), 1, b"bounded unknown")
        root_handle = FakeHandle(IDENTITY); late_handle = FakeHandle(late)
        root_handle.close = MagicMock(); late_handle.close = MagicMock()
        child = MagicMock(pid=17); child.poll.return_value = 0; child.wait.return_value = 0
        deadlines = []
        def resource_census(*args):
            deadlines.append(observer.phase_deadline)
            return ["uncertain-container-census"], [docker_failure]
        def final_census(identity):
            deadlines.append(observer.phase_deadline)
            return [] if len(deadlines) == 1 else [late]
        with tempfile.TemporaryDirectory() as directory, patch.object(observer.sys, "platform", "linux"), patch.object(observer.shutil, "which", return_value="/dotnet"), patch.object(observer.os.path, "realpath", side_effect=lambda path, **kwargs: str(path)), patch.object(observer.os, "pidfd_open", create=True), patch.object(observer.signal, "pidfd_send_signal", create=True), patch.object(observer, "spawn_gated", return_value=(child, root_handle, IDENTITY)), patch.object(observer, "preflight_pidfd"), patch.object(observer, "OwnedHandle", return_value=late_handle), patch.object(observer, "terminal_census", side_effect=final_census) as census, patch.object(observer, "resource_census", side_effect=resource_census):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.run(pathlib.Path(directory))
            self.assertIn(docker_failure, flattened(caught.exception))
            self.assertEqual(2, census.call_count)
            self.assertTrue(all(deadline == deadlines[0] for deadline in deadlines))
            root_handle.close.assert_called_once(); late_handle.close.assert_called_once()
            receipt = json.loads((pathlib.Path(directory) / "outer-process-cleanup.json").read_text())
            self.assertIn(late, receipt["observedProcesses"])
            self.assertIn("process:18", receipt["remaining"])
            self.assertEqual([docker_failure.custody], receipt["commandFailures"])
            self.assertTrue(receipt["errorTypes"])

    def test_exhausted_shared_deadline_refuses_process_census_without_new_lease(self):
        observer.phase_deadline = observer.time.monotonic() - 1
        deadline = observer.phase_deadline
        with patch.object(observer, "process_identity") as read, patch.object(observer.pathlib.Path, "iterdir") as listing:
            with self.assertRaises(TimeoutError): observer.terminal_census(IDENTITY)
        read.assert_not_called(); listing.assert_not_called()
        self.assertEqual(deadline, observer.phase_deadline)

    def test_final_census_deadline_failure_retains_docker_error_and_explicit_uncertainty(self):
        original = OSError("Synthetic Docker census failure")
        terminal_failure = TimeoutError("Synthetic exhausted cleanup budget")
        child = MagicMock(pid=17); child.poll.return_value = 0; child.wait.return_value = 0
        with tempfile.TemporaryDirectory() as directory, patch.object(observer.sys, "platform", "linux"), patch.object(observer.shutil, "which", return_value="/dotnet"), patch.object(observer.os.path, "realpath", side_effect=lambda path, **kwargs: str(path)), patch.object(observer.os, "pidfd_open", create=True), patch.object(observer.signal, "pidfd_send_signal", create=True), patch.object(observer, "spawn_gated", return_value=(child, FakeHandle(IDENTITY), IDENTITY)), patch.object(observer, "preflight_pidfd"), patch.object(observer, "terminal_census", side_effect=[[], terminal_failure]) as census, patch.object(observer, "resource_census", return_value=([], [original])):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.run(pathlib.Path(directory))
            self.assertIn(original, flattened(caught.exception)); self.assertIn(terminal_failure, flattened(caught.exception))
            self.assertEqual(2, census.call_count)
            receipt = json.loads((pathlib.Path(directory) / "outer-process-cleanup.json").read_text())
            self.assertIn("uncertain-process-census", receipt["remaining"])

    def test_late_terminal_child_never_qualifies_cleanup(self):
        late = dict(IDENTITY, pid=18, startTicks=124)
        child = MagicMock(pid=17); child.poll.return_value = 0; child.wait.return_value = 0
        with tempfile.TemporaryDirectory() as directory, patch.object(observer.sys, "platform", "linux"), patch.object(observer.shutil, "which", return_value="/dotnet"), patch.object(observer.os.path, "realpath", side_effect=lambda path, **kwargs: str(path)), patch.object(observer.os, "pidfd_open", create=True), patch.object(observer.signal, "pidfd_send_signal", create=True), patch.object(observer, "spawn_gated", return_value=(child, FakeHandle(IDENTITY), IDENTITY)), patch.object(observer, "preflight_pidfd"), patch.object(observer, "OwnedHandle", FakeHandle), patch.object(observer, "process_identity", return_value=IDENTITY), patch.object(observer, "terminal_census", side_effect=[[late], []]), patch.object(observer, "observe"), patch.object(observer, "docker", return_value=""):
            with self.assertRaises(BaseExceptionGroup) as caught: observer.run(pathlib.Path(directory))
            self.assertTrue(any("Late owned descendant" in str(error) for error in flattened(caught.exception)))




class ResourceAcquisitionControls(unittest.TestCase):
    def setUp(self):
        observer.phase_deadline = observer.time.monotonic() + 30
        self.run = "b" * 32
        self.owned, self.sessions, self.volumes, self.rows = set(), set(), set(), {}

    def resource(self, identity, running=True):
        return {"Id": identity, "Config": {"Labels": {
            "maliev.codex.owner": "procurement-runtime-fixture", "maliev.codex.persistent-data": "false",
            "maliev.codex.parent-run": self.run, "maliev.codex.role": "supplier",
            "maliev.codex.run": "a" * 32, "org.testcontainers.session-id": "c" * 32,
            "maliev.codex.expires-utc": "2026-10-11T09:32:00+00:00"}},
            "Mounts": [{"Type": "volume", "Name": identity}], "Created": "2026-10-11T09:00:00+00:00",
            "State": {"Running": running, "StartedAt": "2026-10-11T09:00:01+00:00", "Pid": 123},
            "HostConfig": {"Memory": 1073741824, "MemorySwap": 1073741824, "NanoCpus": 750000000},
            "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1"}]}}}

    def observe(self):
        observer.observe(self.run, self.owned, self.sessions, self.volumes, self.rows)

    def manual_resource(self, identity):
        row = self.resource(identity)
        row["Config"]["Labels"]["maliev.codex.role"] = "forced-expiry-control"
        del row["Config"]["Labels"]["org.testcontainers.session-id"]
        row["HostConfig"] = {"Memory": 67108864, "MemorySwap": 67108864, "NanoCpus": 100000000}
        row["NetworkSettings"]["Ports"] = {}
        return row

    def test_actual_manual_producer_labels_acquire_without_inventing_tc_session(self):
        producer = (pathlib.Path(__file__).resolve().parents[1] / "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureProviderContainmentTests.cs").read_text(encoding="utf-8")
        contract = producer.split("CreateContainerAsync(new CreateContainerParameters", 1)[1].split("HostConfig =", 1)[0]
        keys = set(re.findall(r'\["([^"]+)"\]\s*=', contract))
        self.assertEqual({"maliev.codex.owner", "maliev.codex.run", "maliev.codex.parent-run",
            "maliev.codex.role", "maliev.codex.expires-utc", "maliev.codex.persistent-data"}, keys)
        self.assertIn('"forced-expiry-control"', contract)
        identity = "a" * 64
        with patch.object(observer, "docker", side_effect=[identity, json.dumps([self.manual_resource(identity)])]):
            self.observe()
        self.assertEqual("docker-api-manual", self.rows[identity]["creationKind"])
        self.assertIsNone(self.rows[identity]["testcontainersSessionId"])
        self.assertFalse(self.sessions)
        self.assertEqual({identity}, self.owned); self.assertEqual({identity}, self.volumes)

    def test_pg_missing_or_invalid_actual_session_never_uses_manual_exception(self):
        identity = "a" * 64
        for session in (None, "", "invalid"):
            row = self.resource(identity)
            if session is None: del row["Config"]["Labels"]["org.testcontainers.session-id"]
            else: row["Config"]["Labels"]["org.testcontainers.session-id"] = session
            with self.subTest(session=session), patch.object(observer, "docker", side_effect=[identity, json.dumps([row])]):
                with self.assertRaises(BaseExceptionGroup): self.observe()
        self.assertFalse(self.rows)

    def test_manual_session_claim_and_pg_role_spoof_still_fail(self):
        identity = "a" * 64
        for mode in ("manual-session", "pg-spoof", "unknown-role"):
            row = self.manual_resource(identity)
            if mode == "manual-session": row["Config"]["Labels"]["org.testcontainers.session-id"] = "c" * 32
            elif mode == "pg-spoof": row["Config"]["Labels"]["maliev.codex.role"] = "supplier"
            else: row["Config"]["Labels"]["maliev.codex.role"] = "unknown"
            with self.subTest(mode=mode), patch.object(observer, "docker", side_effect=[identity, json.dumps([row])]):
                with self.assertRaises(BaseExceptionGroup): self.observe()
        self.assertFalse(self.rows)

    def test_wrong_manual_identity_lease_caps_or_binding_remain_fail_closed(self):
        identity = "a" * 64
        for mode in ("id", "expiry", "caps", "bindings"):
            row = self.manual_resource(identity)
            if mode == "id": row["Id"] = "b" * 64
            elif mode == "expiry": row["Config"]["Labels"]["maliev.codex.expires-utc"] = row["State"]["StartedAt"]
            elif mode == "caps": row["HostConfig"]["Memory"] = 0
            else: row["NetworkSettings"]["Ports"] = {"5432/tcp": [{"HostIp": "127.0.0.1"}]}
            with self.subTest(mode=mode), patch.object(observer, "docker", side_effect=[identity, json.dumps([row])]):
                with self.assertRaises(BaseExceptionGroup): self.observe()
        self.assertFalse(self.rows)

    def test_known_acquired_removed_resource_is_not_reinspected(self):
        identity = "a" * 64
        with patch.object(observer, "docker", side_effect=[identity, json.dumps([self.resource(identity)]), identity, ""] ) as query:
            self.observe(); self.observe(); self.observe()
        self.assertEqual(1, sum(call.args[0] == "inspect" for call in query.call_args_list))
        self.assertEqual({identity}, self.owned)
        self.assertEqual(123, self.rows[identity]["processId"])
        self.assertTrue(all("--no-trunc" in call.args for call in query.call_args_list if call.args[0] == "ps"))

    def test_unknown_removed_resource_fails_without_tombstone_acceptance(self):
        identity = "a" * 64
        original = observer.DockerObservationFailure(("inspect", identity), 1, ("Error: No such object: " + identity).encode())
        with patch.object(observer, "docker", side_effect=[identity, original]):
            with self.assertRaises(BaseExceptionGroup) as caught: self.observe()
        self.assertIn(original, flattened(caught.exception))
        self.assertEqual([original.custody], observer.command_failure_custody([caught.exception]))
        self.assertFalse(self.rows)

    def test_new_full_id_with_same_short_prefix_is_independently_acquired(self):
        first, second = "a" * 64, "a" * 12 + "b" * 52
        with patch.object(observer, "docker", side_effect=[first, json.dumps([self.resource(first)]),
                first + " " + second, json.dumps([self.resource(second)])]) as query:
            self.observe(); self.observe()
        self.assertEqual({first, second}, self.owned)
        self.assertEqual([first, second], [call.args[1] for call in query.call_args_list if call.args[0] == "inspect"])

    def test_short_duplicate_or_inspect_identity_collision_fails(self):
        identity = "a" * 64
        for listing, inspection in [(identity[:12], None), (identity + " " + identity, None),
                (identity, json.dumps([self.resource("b" * 64)]))]:
            with self.subTest(listing=listing), patch.object(observer, "docker", side_effect=[listing, inspection]):
                with self.assertRaises((ValueError, BufferError, BaseExceptionGroup)): self.observe()
        self.assertFalse(self.rows)

    def test_created_resource_is_reinspected_until_running_snapshot_exists(self):
        identity = "a" * 64
        with patch.object(observer, "docker", side_effect=[identity, json.dumps([self.resource(identity, False)]),
                identity, json.dumps([self.resource(identity)])]) as query:
            self.observe(); self.assertFalse(self.rows); self.observe()
        self.assertEqual(2, sum(call.args[0] == "inspect" for call in query.call_args_list))

    def test_wrong_ownership_labels_birth_and_limits_fail_acquisition(self):
        identity = "a" * 64
        for field in ["owner", "parent", "role", "birth", "limits"]:
            row = self.resource(identity)
            if field == "owner": row["Config"]["Labels"]["maliev.codex.owner"] = "foreign"
            elif field == "parent": row["Config"]["Labels"]["maliev.codex.parent-run"] = "d" * 32
            elif field == "role": row["Config"]["Labels"]["maliev.codex.role"] = "foreign"
            elif field == "birth": row["State"]["StartedAt"] = "2026-10-10T09:00:00+00:00"
            else: row["HostConfig"]["Memory"] = 0
            with self.subTest(field=field), patch.object(observer, "docker", side_effect=[identity, json.dumps([row])]):
                with self.assertRaises(BaseExceptionGroup): self.observe()
        self.assertFalse(self.rows)

    def test_multiple_acquisition_errors_preserve_all_and_capture_other_resource(self):
        first, second, third = "a" * 64, "b" * 64, "c" * 64
        one = observer.DockerObservationFailure(("inspect", first), 1, b"bounded unknown")
        two = observer.DockerObservationFailure(("inspect", second), 1, b"bounded unknown")
        with patch.object(observer, "docker", side_effect=[" ".join([first, second, third]), one, two, json.dumps([self.resource(third)])]):
            with self.assertRaises(BaseExceptionGroup) as caught: self.observe()
        self.assertEqual([one, two], flattened(caught.exception))
        self.assertEqual([one.custody, two.custody], observer.command_failure_custody([caught.exception]))
        self.assertIn(third, self.rows)

    def test_acquisition_timeout_preserves_shared_deadline_and_continues_other_resource(self):
        first, second = "a" * 64, "b" * 64
        deadline = observer.phase_deadline
        original = TimeoutError("Synthetic shared deadline")
        with patch.object(observer, "docker", side_effect=[first + " " + second, original, json.dumps([self.resource(second)])]):
            with self.assertRaises(BaseExceptionGroup) as caught: self.observe()
        self.assertIn(original, flattened(caught.exception))
        self.assertEqual(deadline, observer.phase_deadline)
        self.assertIn(second, self.rows)

    def test_terminal_census_attempts_other_queries_and_retains_every_error(self):
        self.sessions.add("c" * 32)
        one, two, three = OSError("acquisition"), TimeoutError("session query"), OSError("global query")
        with patch.object(observer, "observe", side_effect=one), patch.object(observer, "docker",
                side_effect=[two, "late-volume", three, "late-volume"]) as query:
            self.volumes.add("late-volume")
            remaining, errors = observer.resource_census(self.run, self.owned, self.sessions, self.volumes, self.rows)
        self.assertEqual([one, two, three], errors)
        self.assertEqual(4, query.call_count)
        self.assertIn("session-volume:late-volume", remaining)
        self.assertIn("volume:late-volume", remaining)
        self.assertIn("uncertain-container-census", remaining)

    def test_late_session_container_and_volume_still_prevent_terminal_absence(self):
        identity = "a" * 64; self.sessions.add("c" * 32)
        with patch.object(observer, "observe"), patch.object(observer, "docker", side_effect=[identity, "late-volume", "", ""]):
            remaining, errors = observer.resource_census(self.run, self.owned, self.sessions, self.volumes, self.rows)
        self.assertFalse(errors)
        self.assertEqual(["session-container:" + identity, "session-volume:late-volume"], remaining)


class FiniteOriginalCustodyControls(unittest.TestCase):
    def setUp(self):
        eligibility = patch.object(observer, "profile_roles_admitted", True)
        eligibility.start(); self.addCleanup(eligibility.stop)
    def test_unadmitted_profile_role_refused_before_handoff(self):
        fixture, identity, row = self.profile_row()
        with patch.object(observer, "profile_roles_admitted", False), patch.object(observer, "docker", side_effect=[identity, json.dumps([row])]), patch.object(observer, "publish_recovery_scope") as publish:
            with self.assertRaises(BaseExceptionGroup): fixture.observe()
            publish.assert_not_called()
        self.assertNotIn(identity, fixture.rows)

    def rows(self):
        import copy
        row={"Id":"a"*64,"Image":"sha256:"+"b"*64,"Created":"2026-10-12T00:00:00Z", "Config":{"Labels":{"maliev.codex.expires-utc":"2026-10-12T00:00:30Z"},"Entrypoint":["sh"],"Cmd":[]},"Mounts":[{"Name":"original"}],"State":{"StartedAt":"2026-10-12T00:00:01Z","Pid":17,"Running":True}}
        return row,copy.deepcopy(row)
    def profile_row(self):
        fixture=ResourceAcquisitionControls();fixture.setUp();identity="d"*64;row=fixture.manual_resource(identity)
        row["Image"]="sha256:"+"e"*64
        row["Config"]["Labels"]["maliev.codex.role"]="expiry-profile-bookworm"
        row["Config"]["Labels"]["maliev.codex.expires-utc"]="2026-10-11T09:00:30+00:00"
        row["Config"].update(Entrypoint=["sh","-c",'exec timeout --signal=INT --kill-after=1s 2 "$@"',"procurement-expiry-profile"],Cmd=["sh","-c",'trap "" INT TERM; while :; do sleep 1; done'])
        row["Mounts"][0].update(Destination="/data",RW=True)
        row["NetworkSettings"]["Ports"]={"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"32769"}]}
        return fixture,identity,row
    def test_refused_binding_retains_original_scope_but_no_recovery(self):
        fixture,identity,row=self.profile_row();row["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostIp"]="0.0.0.0"
        with patch.object(observer,"docker",side_effect=[identity,json.dumps([row])]),patch.object(observer,"publish_recovery_scope") as publish:
            with self.assertRaises(BaseExceptionGroup):fixture.observe()
            publish.assert_not_called()
        self.assertIn(identity,fixture.rows);self.assertFalse(fixture.rows[identity]["acquisitionEligible"])
        self.assertEqual("0.0.0.0",fixture.rows[identity]["finiteOwnerProfileScope"]["hostBindings"]["5432/tcp"][0]["HostIp"])
    def test_only_valid_original_scope_handed_to_owner(self):
        fixture,identity,row=self.profile_row()
        with patch.object(observer,"docker",side_effect=[identity,json.dumps([row])]),patch.object(observer,"publish_recovery_scope") as publish:
            fixture.observe();publish.assert_called_once()
        self.assertTrue(fixture.rows[identity]["acquisitionEligible"])
    def test_original_lease_label_drift_refused(self):
        before,after=self.rows();after["Config"]["Labels"]["maliev.codex.expires-utc"]="2026-10-12T00:00:31Z"
        with self.assertRaises(ValueError):observer.immutable_finite_scope(before,after)
    def test_birth_drift_after_stop_refused(self):
        before,after=self.rows();after["State"].update(Running=False,StartedAt="2026-10-12T00:00:02Z")
        with self.assertRaises(ValueError):observer.immutable_finite_scope(before,after)
    def test_natural_stop_race_requires_same_immutable_birth(self):
        before,after=self.rows();after["State"].update(Running=False,Pid=0)
        self.assertTrue(observer.immutable_finite_scope(before,after))
        after["Created"]="2026-10-12T00:00:01Z"
        with self.assertRaises(ValueError):observer.immutable_finite_scope(before,after)

if __name__ == "__main__": unittest.main()


class NativeMemoryAdmissionControls(unittest.TestCase):
    def reading(self, raw):
        from unittest.mock import mock_open
        with patch.object(observer.sys,'platform','linux'),patch('builtins.open',mock_open(read_data=raw)) as opened,patch('builtins.print'):
            receipt=observer.require_native_memory()
            opened.assert_called_once_with('/proc/meminfo','rb')
            opened().read.assert_called_once_with(4097)
            opened().__exit__.assert_called_once()
            return receipt

    def test_exact_3gib_floor_and_higher_admit_without_override(self):
        for available in [3145728,3145729,4194304]:
            receipt=self.reading(('MemTotal: 9999999 kB\nMemAvailable: '+str(available)+' kB\n').encode())
            self.assertEqual(available,receipt['availableKiB']);self.assertEqual(3145728,receipt['minimumKiB'])

    def test_missing_duplicate_wrong_units_negative_or_malformed_refused(self):
        for raw in [b'',b'MemFree: 9999999 kB',b'MemAvailable: 9999999 kB\nMemAvailable: 9999999 kB',b'MemAvailable: 4 GiB',b'MemAvailable: -1 kB',b'MemAvailable: 3.5 kB',b'MemAvailable: 9999999 kB extra',b'MemAvailable: unavailable kB',b'MemAvailable: 99999999999999999 kB']:
            with self.subTest(raw=raw),self.assertRaises(RuntimeError):self.reading(raw)

    def test_below_floor_and_oversized_source_refused(self):
        for raw in [b'MemAvailable: 3145727 kB',b'MemAvailable: 0 kB',b'MemAvailable: 9999999 kB\n'+b'x'*4096]:
            with self.subTest(raw=raw[:40]),self.assertRaises(RuntimeError):self.reading(raw)

    def test_unavailable_and_unsupported_fail_closed_without_subprocess(self):
        with patch.object(observer.sys,'platform','win32'),patch('builtins.open') as opened,patch.object(observer.subprocess,'Popen') as child:
            with self.assertRaises(RuntimeError):observer.require_native_memory()
            opened.assert_not_called();child.assert_not_called()
        with patch.object(observer.sys,'platform','linux'),patch('builtins.open',side_effect=OSError('unavailable')),patch.object(observer.subprocess,'Popen') as child:
            with self.assertRaises(RuntimeError):observer.require_native_memory()
            child.assert_not_called()

    def test_fresh_second_read_cannot_reuse_prior_high_memory(self):
        from unittest.mock import mock_open
        handle=mock_open();handle.return_value.read.side_effect=[b'MemAvailable: 4194304 kB',b'MemAvailable: 3145727 kB']
        with patch.object(observer.sys,'platform','linux'),patch('builtins.open',handle),patch('builtins.print'):
            observer.require_native_memory()
            with self.assertRaises(RuntimeError):observer.require_native_memory()
            self.assertEqual(2,handle.call_count)

    def test_low_memory_entry_refuses_before_helpers_roles_or_docker(self):
        from unittest.mock import mock_open
        with patch.object(observer.sys,'platform','linux'),patch('builtins.open',mock_open(read_data=b'MemAvailable: 3145727 kB')),patch.object(observer,'preflight_pidfd') as helper,patch.object(observer,'native_extension') as roles,patch.object(observer,'spawn_gated') as native,patch.object(observer,'docker') as docker,patch.object(observer.pathlib.Path,'mkdir') as mkdir:
            with self.assertRaisesRegex(RuntimeError,'3145728'):observer.run(pathlib.Path('never-created'))
            helper.assert_not_called();roles.assert_not_called();native.assert_not_called();docker.assert_not_called();mkdir.assert_not_called()
