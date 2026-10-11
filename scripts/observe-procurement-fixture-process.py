"""Linux hosted witness: observe only, never remove containers or foreign processes."""
import hashlib
import re
import datetime
import json
import os
import pathlib
import signal
import select
import subprocess
import shutil
import sys
import time
import uuid

MAX_OUTPUT_BYTES = 1024 * 1024
MAX_ERROR_BYTES = 65536
MAX_PROC_BYTES = 4096
MAX_PROCESSES = 4096
MAX_RESOURCES = 64
phase_deadline = 0.0
phase_name = "not-started"


def remaining_timeout(maximum):
    remaining = phase_deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Observer phase deadline exceeded")
    return min(maximum, remaining)


class OwnedHandle:
    def __init__(self, identity):
        self.identity = identity
        self.fd = os.pidfd_open(identity["pid"])
        self.approved_executables = {identity["executable"]}
        try:
            if process_identity(identity["pid"]) != identity:
                raise RuntimeError("PID birth/executable changed while retaining exact handle")
        except BaseException as primary:
            try: os.close(self.fd)
            except BaseException as cleanup:
                raise BaseExceptionGroup("Handle binding and close failures", [primary, cleanup])
            raise

    def send(self, signum):
        actual = process_identity(self.identity["pid"])
        if actual is None or any(actual[key] != self.identity[key] for key in ("pid", "startTicks", "group", "session")) or actual["executable"] not in self.approved_executables:
            raise RuntimeError("PID identity changed; signal refused")
        signal.pidfd_send_signal(self.fd, signum)

    def exited(self):
        return bool(select.select([self.fd], [], [], 0)[0])

    def close(self):
        os.close(self.fd)


def preflight_pidfd():
    # SIG0 checks the actual kernel syscall and permission without delivering a signal.
    fd = os.pidfd_open(os.getpid())
    primary = None
    try: signal.pidfd_send_signal(fd, 0)
    except BaseException as error: primary = error
    try: os.close(fd)
    except BaseException as cleanup:
        if primary is not None: raise BaseExceptionGroup("Preflight and handle close failures", [primary, cleanup])
        raise
    if primary is not None: raise primary


GATE_SCRIPT = """import json,os,resource,select,sys
reader=int(sys.argv[1]); command=json.loads(sys.argv[2])
resource.setrlimit(resource.RLIMIT_CPU,(600,660))
ready=select.select([reader],[],[],5)[0]
admitted=os.read(reader,1)==b'G' if ready else False
os.close(reader)
if not admitted: sys.exit(125)
os.execv(command[0],command)
"""


def spawn_gated(command, acquisition_deadline=None, **kwargs):
    acquisition_deadline = phase_deadline if acquisition_deadline is None else min(acquisition_deadline, phase_deadline)
    def require_gate_reserve():
        if acquisition_deadline - time.monotonic() < 6:
            raise TimeoutError("Insufficient phase budget for five-second holding gate and settlement")
    require_gate_reserve()
    preflight_pidfd()
    executable = shutil.which(command[0])
    if executable is None: raise RuntimeError("Reviewed executable is unavailable")
    command = [os.path.realpath(executable), *command[1:]]
    require_gate_reserve()
    reader, writer = os.pipe()
    child, handle, identity = None, None, None
    failures = []
    admitted = False
    try:
        require_gate_reserve()
        child = subprocess.Popen([sys.executable, "-I", "-S", "-B", "-c", GATE_SCRIPT, str(reader), json.dumps(command)],
                                 pass_fds=(reader,), start_new_session=True, **kwargs)
        identity = process_identity(child.pid)
        if identity is None: raise RuntimeError("Gated child birth was not observed")
        handle = OwnedHandle(identity)
        handle.approved_executables.add(command[0])
        if os.write(writer, b"G") != 1:
            raise IOError("Native admission byte was not written completely")
        admitted = True
    except BaseException as error:
        failures.append(error)
    finally:
        for fd in (reader, writer):
            try: os.close(fd)
            except BaseException as error: failures.append(error)
    if failures:
        # No admission byte is sent before exact-handle custody. The unadmitted gate exits
        # on EOF or its five-second deadline; acquisition failure never executes native work.
        if admitted and handle is not None:
            try:
                if not handle.exited(): handle.send(signal.SIGKILL)
            except BaseException as error: failures.append(error)
        if child is not None:
            try:
                budget = acquisition_deadline - time.monotonic()
                if budget <= 0: raise TimeoutError("Gated child custody remains unsettled at acquisition deadline")
                child.wait(timeout=min(6, budget))
            except BaseException as error: failures.append(error)
        if child is not None:
            for name in ("stdin", "stdout", "stderr"):
                stream = getattr(child, name, None)
                if stream is not None:
                    try: stream.close()
                    except BaseException as error: failures.append(error)
        if handle is not None:
            try: handle.close()
            except BaseException as error: failures.append(error)
        raise BaseExceptionGroup("Gated acquisition and cleanup failures", failures)
    return child, handle, identity


class DockerObservationFailure(RuntimeError):
    def __init__(self, command, exit_code, error, launch=None):
        target = command[1] if len(command) == 2 and command[0] == "inspect" and re.fullmatch(r"[a-f0-9]{12,64}", command[1]) else None
        query = "inspect-container" if target else "list-containers" if command[0] == "ps" else "list-volumes" if command[:2] == ("volume", "ls") else "unknown-query"
        missing = target is not None and re.fullmatch(rb"(?:Error response from daemon: |Error: )No such (?:object|container): " + target.encode() + rb"\s*", error) is not None
        self.custody = {"query": query, "containerId": target, "exitCode": exit_code,
                        "category": "exact-container-not-found" if missing else "unclassified-command-failure",
                        "stderrBytes": len(error), "stderrSha256": hashlib.sha256(error).hexdigest(),
                        "phase": phase_name, "commandLaunchProcess": launch, "durationMilliseconds": 0,
                        "childTerminalObserved": False, "streamsClosed": False, "handleClosed": False}
        super().__init__("Read-only Docker command failed; sanitized custody retained")


def command_failure_custody(errors):
    rows = []
    def visit(error):
        if isinstance(error, DockerObservationFailure): rows.append(dict(error.custody))
        if isinstance(error, BaseExceptionGroup):
            for child in error.exceptions: visit(child)
    for error in errors: visit(error)
    return rows


def docker(*args):
    command_started = time.monotonic()
    allocation = remaining_timeout(10)
    deadline = time.monotonic() + allocation - min(1, allocation / 2)
    child, handle, identity = spawn_gated(["docker", "--host", "unix:///var/run/docker.sock", *args], acquisition_deadline=deadline, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    failures, output, error_output = [], bytearray(), bytearray()
    terminal_observed, streams_closed, handle_closed = False, 0, False
    try:
        streams = [(child.stdout, output, MAX_OUTPUT_BYTES), (child.stderr, error_output, MAX_ERROR_BYTES)]
        completed = set()
        for stream, _, _ in streams: os.set_blocking(stream.fileno(), False)
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("Docker observation command deadline exceeded")
            for index, (stream, content, limit) in enumerate(streams):
                if index in completed: continue
                try: chunk = os.read(stream.fileno(), min(65536, limit + 1 - len(content)))
                except BlockingIOError: chunk = None
                if chunk:
                    content.extend(chunk)
                    if len(content) > limit: raise BufferError("Docker observation output exceeded byte limit")
                elif chunk == b"": completed.add(index)
            if len(completed) == 2 and child.poll() is not None: break
            time.sleep(min(0.05, remaining_timeout(0.05)))
        if child.returncode:
            raise DockerObservationFailure(args, child.returncode, bytes(error_output), dict(identity))
    except BaseException as error:
        failures.append(error)
    finally:
        try:
            if handle is not None and not handle.exited():
                handle.send(signal.SIGTERM)
                grace = max(0, min(0.25, phase_deadline - time.monotonic() - 0.25))
                if not select.select([handle.fd], [], [], grace)[0]:
                    handle.send(signal.SIGKILL)
        except BaseException as error:
            failures.append(error)
        try:
            child.wait(timeout=remaining_timeout(1))
            terminal_observed = True
        except BaseException as error:
            failures.append(error)
        for stream in (child.stdout, child.stderr):
            try:
                stream.close()
                streams_closed += 1
            except BaseException as error: failures.append(error)
        if handle is not None:
            try:
                handle.close()
                handle_closed = True
            except BaseException as error: failures.append(error)
    for failure in failures:
        if isinstance(failure, DockerObservationFailure):
            failure.custody.update(durationMilliseconds=max(0, int((time.monotonic() - command_started) * 1000)), childTerminalObserved=terminal_observed, streamsClosed=streams_closed == 2, handleClosed=handle_closed)
    if failures:
        raise BaseExceptionGroup("Docker observer command and cleanup failures", failures)
    return output.decode("utf-8", errors="strict")


def process_identity(pid, executable=True):
    try:
        with pathlib.Path(f"/proc/{pid}/stat").open("rb") as stream:
            raw = stream.read(MAX_PROC_BYTES + 1)
        if len(raw) > MAX_PROC_BYTES:
            raise BufferError("Process identity exceeded byte limit")
        data = raw.decode()
        fields = data[data.rindex(")") + 2:].split()
        result = {"pid": pid, "startTicks": int(fields[19]), "group": int(fields[2]), "session": int(fields[3])}
        if executable:
            result["executable"] = os.readlink(f"/proc/{pid}/exe")
            if len(result["executable"]) > MAX_PROC_BYTES:
                raise BufferError("Process executable exceeded byte limit")
        return result
    except FileNotFoundError:
        return None


def terminal_census(identity):
    remaining_timeout(1)
    leader = process_identity(identity["pid"])
    if leader is not None and any(leader[key] != identity[key] for key in ("pid", "startTicks", "group", "session")) and leader["group"] == identity["group"] and leader["session"] == identity["session"]:
        raise RuntimeError("Owned session leader identity reused; census uncertain")
    rows = []
    count = 0
    for entry in pathlib.Path("/proc").iterdir():
        remaining_timeout(1)
        if not entry.name.isdecimal():
            continue
        count += 1
        if count > MAX_PROCESSES:
            raise BufferError("Process census exceeded cardinality bound")
        actual = process_identity(int(entry.name), executable=False)
        if actual is not None and actual["group"] == identity["group"] and actual["session"] == identity["session"]:
            first = actual
            actual = process_identity(int(entry.name))
            if actual is not None:
                if any(actual[key] != first[key] for key in ("pid", "startTicks", "group", "session")):
                    raise RuntimeError("Owned census identity changed between samples; handle refused")
                stable = process_identity(int(entry.name))
                if stable != actual:
                    raise RuntimeError("Owned census executable or birth changed; handle refused")
                if actual["startTicks"] < identity["startTicks"]:
                    raise RuntimeError("Owned session contains uncertain older process")
                rows.append(actual)
                if len(rows) > MAX_RESOURCES:
                    raise BufferError("Owned process cardinality exceeded")
    return rows


OBSERVATION_CONTRACT = "one-running-snapshot-full-id-census-v1"


def observe(run, owned, sessions, volumes, observations):
    ids = docker("ps", "-aq", "--no-trunc", "--filter", "label=maliev.codex.parent-run=" + run).split()
    if len(ids) > MAX_RESOURCES or len(set(ids)) != len(ids):
        raise BufferError("Owned container census exceeded bound or duplicated identity")
    failures = []
    for identity in ids:
        try:
            if not re.fullmatch(r"[a-f0-9]{64}", identity):
                raise ValueError("Container census requires full immutable identities")
            # Only a previously acquired RUNNING snapshot permits skipping inspection.
            # This contract never claims continuous caps/label/birth monitoring.
            if identity in observations:
                continue
            rows = json.loads(docker("inspect", identity))
            if len(rows) != 1 or rows[0]["Id"] != identity:
                raise ValueError("Acquisition identity differs from full-ID census")
            row = rows[0]
            labels = row["Config"]["Labels"]
            role = labels.get("maliev.codex.role")
            if labels.get("maliev.codex.owner") != "procurement-runtime-fixture" or labels.get("maliev.codex.persistent-data") != "false" or labels.get("maliev.codex.parent-run") != run or role not in ("supplier", "purchase-order", "forced-expiry-control"):
                raise ValueError("Owned observation label mismatch")
            resource_run = labels.get("maliev.codex.run")
            session = labels.get("org.testcontainers.session-id")
            uuid.UUID(hex=resource_run)
            uuid.UUID(hex=session)
            forced = role == "forced-expiry-control"
            memory = 67108864 if forced else 1073741824
            cpu = 100000000 if forced else 750000000
            if row["HostConfig"]["Memory"] != memory or row["HostConfig"]["MemorySwap"] != memory or row["HostConfig"]["NanoCpus"] != cpu:
                raise ValueError("Independent acquisition limits differ")
            if len(row["Mounts"]) > MAX_RESOURCES:
                raise BufferError("Owned mount cardinality exceeded")
            row_volumes = [mount["Name"] for mount in row["Mounts"] if mount["Type"] == "volume"]
            if not row_volumes or any(not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name) for name in row_volumes):
                raise ValueError("Independent volume acquisition missing or unsafe")
            owned.add(identity); sessions.add(session); volumes.update(row_volumes)
            if len(owned) > MAX_RESOURCES or len(sessions) > MAX_RESOURCES or len(volumes) > MAX_RESOURCES:
                raise BufferError("Owned resource metadata cardinality exceeded")
            if row["State"]["Running"]:
                host_ips = [binding["HostIp"] for bindings in (row["NetworkSettings"]["Ports"] or {}).values() for binding in (bindings or [])]
                if len(host_ips) > MAX_RESOURCES or (host_ips != [] if forced else set(host_ips) != {"127.0.0.1"}):
                    raise ValueError("Independent acquisition binding differs")
                created = datetime.datetime.fromisoformat(row["Created"].replace("Z", "+00:00"))
                started = datetime.datetime.fromisoformat(row["State"]["StartedAt"].replace("Z", "+00:00"))
                expires = datetime.datetime.fromisoformat(labels["maliev.codex.expires-utc"].replace("Z", "+00:00"))
                if started < created or expires <= started or type(row["State"]["Pid"]) is not int or row["State"]["Pid"] <= 0:
                    raise ValueError("Independent acquisition birth or lease differs")
                observations[identity] = {"id": identity, "role": role,
                    "resourceRunId": resource_run, "parentRunId": run,
                    "createdAt": row["Created"], "startedAt": row["State"]["StartedAt"],
                    "processId": row["State"]["Pid"], "memoryBytes": row["HostConfig"]["Memory"],
                    "memorySwapBytes": row["HostConfig"]["MemorySwap"], "nanoCpus": row["HostConfig"]["NanoCpus"],
                    "expiresAt": labels["maliev.codex.expires-utc"], "volumes": row_volumes, "hostIps": host_ips}
        except BaseException as error:
            failures.append(error)
    if failures:
        raise BaseExceptionGroup("Independent resource acquisition failures", failures)


def resource_census(run, owned, sessions, volumes, observations):
    remaining, failures = [], []
    try: observe(run, owned, sessions, volumes, observations)
    except BaseException as error: failures.append(error)
    for session in sorted(sessions):
        for kind, command in (
            ("session-container", ("ps", "-aq", "--no-trunc", "--filter", "label=org.testcontainers.session-id=" + session)),
            ("session-volume", ("volume", "ls", "-q", "--filter", "label=org.testcontainers.session-id=" + session))):
            try:
                values = docker(*command).split()
                if len(values) > MAX_RESOURCES:
                    raise BufferError("Session census cardinality exceeded")
                if kind == "session-container" and any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in values):
                    raise ValueError("Session census requires full container identities")
                remaining.extend(kind + ":" + value for value in values)
            except BaseException as error:
                failures.append(error); remaining.append("uncertain-" + kind + "-census")
    for kind, known, command in (("container", owned, ("ps", "-aq", "--no-trunc")), ("volume", volumes, ("volume", "ls", "-q"))):
        try:
            values = set(docker(*command).split())
            if len(values) > MAX_PROCESSES:
                raise BufferError("Terminal Docker census cardinality exceeded")
            if kind == "container" and any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in values):
                raise ValueError("Terminal census requires full container identities")
            remaining.extend(kind + ":" + value for value in sorted(known & values))
        except BaseException as error:
            failures.append(error); remaining.append("uncertain-" + kind + "-census")
    return remaining, failures


def process_custody(launch, expected, observed):
    root = next((row for row in observed if row["pid"] == launch["pid"] and row["executable"] == expected), None) if launch is not None else None
    if root is None or any(root[key] != launch[key] for key in ("pid", "startTicks", "group", "session")):
        raise RuntimeError("Authorized native executable transition was not observed with exact launch birth")
    return {"launchProcess": dict(launch), "expectedTestExecutable": expected, "testProcess": dict(root)}


def record_process(processes, actual, launch, expected):
    if actual["pid"] == launch["pid"]:
        if any(actual[key] != launch[key] for key in ("pid", "startTicks", "group", "session")) or actual["executable"] not in (launch["executable"], expected):
            raise RuntimeError("Unapproved native executable transition or reused launch identity")
    processes[actual["pid"]] = actual


def run(root):
    global phase_deadline, phase_name
    if sys.platform != "linux":
        raise RuntimeError("Independent witness requires hosted Linux /proc")
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError("Race-safe Linux pidfd ownership is required")
    preflight_pidfd()
    root.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    env = dict(os.environ, MALIEV_TEST_RESOURCE_RUN_ID=run_id,
               VSTestResultsDirectory=str(root.resolve()), GITHUB_ACTIONS="false",
               DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER="1", MSBUILDDISABLENODEREUSE="1")
    command = ["dotnet", "test", "Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj",
               "--configuration", "Release", "--no-build", "--no-restore", "-p:UseLocalMalievDependencies=true",
               "--filter", "FullyQualifiedName~ProcurementFixtureLifetimeTests|FullyQualifiedName~ProcurementFixtureProviderContainmentTests",
               "--logger", "trx", "--results-directory", str(root.resolve())]
    owned, sessions, volumes, processes, errors = set(), set(), set(), {}, []
    observations = {}
    handles = {}
    primary = None
    child = None
    log = None
    identity = None
    expected_executable = None
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        phase_name = "native-observation"
        phase_deadline = time.monotonic() + 600
        log = (root / "native-test.log").open("w")
        executable = shutil.which(command[0])
        if executable is None: raise RuntimeError("Reviewed native executable unavailable")
        expected_executable = os.path.realpath(executable)
        child, native_handle, identity = spawn_gated(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        processes[child.pid] = identity
        handles[child.pid] = native_handle
        deadline = phase_deadline
        while child.poll() is None:
            if time.monotonic() >= deadline:
                raise TimeoutError("Native focused execution deadline exceeded")
            observe(run_id, owned, sessions, volumes, observations)
            for actual in terminal_census(identity):
                if actual["pid"] not in handles:
                    handles[actual["pid"]] = OwnedHandle(actual)
                record_process(processes, actual, identity, expected_executable)
            time.sleep(0.1)
        if child.returncode:
            raise RuntimeError("Native focused test process failed")
    except BaseException as error:
        primary = error
        errors.append(error)
    finally:
        phase_name = "cleanup-observation"
        phase_deadline = time.monotonic() + 20
        if identity is not None:
            try:
                # Fresh terminal census includes children born after the last running sample.
                for actual in terminal_census(identity):
                    if actual["pid"] not in handles:
                        errors.append(RuntimeError("Late owned descendant prevents qualification"))
                        handles[actual["pid"]] = OwnedHandle(actual)
                    record_process(processes, actual, identity, expected_executable)
            except BaseException as error:
                errors.append(error)
        remaining = []
        natural_process_deadline = time.monotonic() + 10
        for recorded in processes.values():
            try:
                handle = handles[recorded["pid"]]
                while not handle.exited() and time.monotonic() < natural_process_deadline:
                    time.sleep(0.1)
                if not handle.exited():
                    errors.append(RuntimeError("Unsettled owned process prevents qualification"))
                    handle.send(signal.SIGTERM)
                    stop_deadline = time.monotonic() + 5
                    while not handle.exited() and time.monotonic() < stop_deadline and time.monotonic() < phase_deadline:
                        time.sleep(0.1)
                    if not handle.exited():
                        handle.send(signal.SIGKILL)
            except ProcessLookupError:
                pass
            except BaseException as error:
                errors.append(error)
        try:
            # This independent observer never deletes a resource; failed cleanup stays visible.
            natural_resource_deadline = phase_deadline
            while True:
                remaining = []
                remaining, census_failures = resource_census(run_id, owned, sessions, volumes, observations)
                if census_failures:
                    raise BaseExceptionGroup("Independent terminal resource census failures", census_failures)
                if not remaining or time.monotonic() >= natural_resource_deadline:
                    break
                time.sleep(0.2)
        except BaseException as error:
            errors.append(error)
        # Final process observation is independent of every Docker acquisition/census failure.
        # It shares the existing deadline and never grants a new cleanup interval.
        if identity is not None:
            try:
                for actual in terminal_census(identity):
                    remaining.append("process:" + str(actual["pid"]))
                    try:
                        if actual["pid"] not in handles:
                            errors.append(RuntimeError("Unobserved terminal descendant prevents qualification"))
                            handles[actual["pid"]] = OwnedHandle(actual)
                        record_process(processes, actual, identity, expected_executable)
                    except BaseException as error:
                        errors.append(error)
            except BaseException as error:
                remaining.append("uncertain-process-census")
                errors.append(error)
        exit_code = None
        if child is not None:
            try:
                exit_code = child.poll()
            except BaseException as error:
                errors.append(error)
            try:
                child.wait(timeout=remaining_timeout(1))
            except BaseException as error:
                errors.append(error)
        if log is not None:
            try: log.close()
            except BaseException as error: errors.append(error)
        for handle in handles.values():
            try: handle.close()
            except BaseException as error: errors.append(error)
        observed_processes = list(processes.values())
        if identity is not None and identity not in observed_processes:
            observed_processes.insert(0, dict(identity))
        custody = {"launchProcess": identity, "expectedTestExecutable": expected_executable, "testProcess": None}
        try: custody = process_custody(identity, expected_executable, observed_processes)
        except BaseException as error: errors.append(error)
        receipt = {"schemaVersion": 2, "observationContract": OBSERVATION_CONTRACT, "runId": run_id, "startedAtUtc": started,
                   "completedAtUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   **custody, "testExitCode": exit_code,
                   "observedProcesses": observed_processes, "ownedContainers": sorted(owned),
                   "observedResources": list(observations.values()),
                   "ownedVolumes": sorted(volumes), "sessions": sorted(sessions),
                   "remaining": remaining, "errorTypes": [type(error).__name__ for error in errors], "commandFailures": command_failure_custody(errors), "destructiveDockerActions": 0}
        try:
            (root / "outer-process-cleanup.json").write_text(json.dumps(receipt, indent=2) + "\n")
        except BaseException as error:
            errors.append(error)
    if primary is not None or errors or remaining or not owned or not sessions:
        if not errors:
            errors.append(RuntimeError("Focused run or independent cleanup custody is incomplete"))
        raise BaseExceptionGroup("Focused run and all independent cleanup/publication failures", errors)


if __name__ == "__main__":
    run(pathlib.Path(sys.argv[1]))
