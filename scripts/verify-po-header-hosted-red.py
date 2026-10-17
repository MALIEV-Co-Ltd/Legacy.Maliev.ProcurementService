"""Hosted-only PO header RED control; no source host/original runtime or coverage claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
import uuid
import xml.etree.ElementTree as ET

PROJECT = "Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj"
SOLUTION = "Legacy.Maliev.ProcurementService.slnx"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout


def safe_path(root, relative):
    path = root / relative
    require(not path.is_symlink() and path.resolve().is_relative_to(root), "Unsafe packet path")
    return path


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def hosted_context():
    require(sys.version_info >= (3, 11), "Existing hosted Python 3.11+ required")
    require(os.environ.get("GITHUB_ACTIONS") == "true", "Hosted GitHub Actions only")
    require(os.environ.get("RUNNER_OS") == "Linux", "Existing Linux validation job only")
    root = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    require(Path.cwd().resolve() == root, "Run at the ephemeral checkout root")
    contract_path = root / "docs/procurement-po-header-hosted-red-contract.json"
    contract_bytes = contract_path.read_bytes()
    require(contract_bytes == git(root, "show", "HEAD:docs/procurement-po-header-hosted-red-contract.json"),
            "Contract differs from current HEAD")
    return root, json.loads(contract_bytes), contract_bytes


def binding_digest(value):
    require(isinstance(value, dict) and set(value) == {"sha256"}
            and isinstance(value["sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None,
            "Require one explicit public SHA256 provenance record")
    return value["sha256"]


def require_header_binding_advance(contract, current):
    header = "Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderHeaderRequestJsonConverter.cs"
    tests = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementPurchaseOrderHeaderBindingTests.cs"
    expected = {header, tests}
    prior = contract["previousHeaderIgnoredFieldBindings"]
    advance = contract["headerIgnoredFieldBindingAdvance"]
    require(isinstance(prior, dict) and set(prior) == set(current)
            and isinstance(advance, dict) and advance.get("issue") == 70
            and advance.get("base") == "44c79ed24c142883563e037bbb5be724ea87322a"
            and advance.get("bindingFormat") == "sha256-record-v1",
            "Require exact reviewed header binding generation")
    pre, post = advance["preimages"], advance["postimages"]
    require(isinstance(pre, dict) and isinstance(post, dict)
            and set(pre) == set(post) == expected, "Require only the two reviewed header bindings")
    old = {path: binding_digest(record) for path, record in prior.items()}
    known_pre = {
        header: "d889daf8f8c8adeb10291476b592184f8a1551f170bc8a527888ff4f6c7bec0e",
        tests: "444a71c704d94fc5d8e5b4eaa100d06b0fe3e5e2ff544b4af31e0e94b62d1c9e",
    }
    require({path for path in current if current[path] != old[path]} == expected,
            "Unrelated header witness source binding changed")
    for path in expected:
        require(binding_digest(pre[path]) == old[path] == known_pre[path]
                and binding_digest(post[path]) == current[path],
                "Header successor detached from exact pre/postimage")
    return expected


def candidate_digests(contract):
    require(contract.get("candidateBindingFormat") == "sha256-record-v1",
            "Require the reviewed SHA256 provenance format")
    bindings = contract["candidateBindings"]
    require(isinstance(bindings, dict) and len(bindings) == 9,
            "Require all nine reviewed current source bindings")
    current = {relative: binding_digest(record) for relative, record in bindings.items()}
    require_header_binding_advance(contract, current)
    return current


def candidate_sources(root, contract):
    sources = {}
    for relative, expected in candidate_digests(contract).items():
        data = git(root, "show", "HEAD:" + relative)
        require(digest(data) == expected, "Reviewed candidate HEAD source changed: " + relative)
        sources[relative] = data
    return sources


def restore(root, contract, sources, evidence, head):
    settle_command_groups(evidence)
    require(git(root, "rev-parse", "HEAD").decode().strip() == head, "HEAD changed during RED control")
    reviewed_digests = candidate_digests(contract)
    for relative in (contract["baseline"]["programPath"], contract["baseline"]["absentPath"]):
        safe_path(root, relative).write_bytes(sources[relative])
    restored = {}
    for relative, expected in reviewed_digests.items():
        actual = digest(safe_path(root, relative).read_bytes())
        require(actual == expected, "Candidate restoration mismatch: " + relative)
        restored[relative] = {"sha256": actual}
    require(not git(root, "status", "--porcelain", "--untracked-files=no").strip(),
            "Tracked checkout still differs after candidate restoration")
    save(evidence / "restoration.json", {"head": head, "restored": restored, "trackedClean": True})


def boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()


def process_identity(pid):
    try:
        path = Path("/proc") / str(pid)
        fields = (path / "stat").read_text(encoding="utf-8").rsplit(") ", 1)[1].split()
        return {"pid": pid, "state": fields[0], "group": int(fields[2]),
                "session": int(fields[3]), "startTicks": int(fields[19]), "uid": path.stat().st_uid}
    except (FileNotFoundError, ProcessLookupError):
        return None


def group_members(custody):
    require(custody["bootId"] == boot_id() and custody["ownerUid"] == os.getuid()
            and custody["ownerRunId"] == os.environ.get("GITHUB_RUN_ID")
            and custody["ownerJob"] == os.environ.get("GITHUB_JOB"), "Command custody changed")
    if not custody["started"]:
        require(custody["verifiedAbsent"] and custody["leaderPid"] is None,
                "Interrupted command launch; restoration/rebuild blocked")
        return []
    require(custody["leaderStartTicks"] is not None, "Unproven command start identity")
    members = []
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        identity = process_identity(int(path.name))
        require(identity is None or identity["session"] != custody["session"]
                or identity["group"] == custody["group"], "Untracked group in owned session; preserve and block")
        if identity is None or identity["group"] != custody["group"]:
            continue
        require(identity["session"] == custody["session"] and identity["uid"] == custody["ownerUid"]
                and identity["startTicks"] >= custody["leaderStartTicks"], "Foreign group member; preserve")
        if identity["pid"] == custody["leaderPid"]:
            require(identity["startTicks"] == custody["leaderStartTicks"], "Leader PID reused; preserve")
        members.append(identity)
    return members


def cleanup_group(custody, process=None):
    def observe():
        if process is not None:
            process.poll()  # Reap our leader before absence checks.
        return group_members(custody)

    def wait_absent(seconds):
        deadline = time.monotonic() + seconds
        while observe():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)
        return True

    if not observe():
        return
    # Every signal follows a fresh custody/membership check of this private session.
    if observe():
        try:
            os.killpg(custody["group"], signal.SIGTERM)
        except ProcessLookupError:
            pass
    if wait_absent(10):
        return
    if observe():
        try:
            os.killpg(custody["group"], signal.SIGKILL)
        except ProcessLookupError:
            pass
    require(wait_absent(10), "Owned command group remains; source restoration/rebuild blocked")


def settle_command_groups(evidence):
    for path in sorted(evidence.glob("*-resource.json")):
        custody = json.loads(path.read_text(encoding="utf-8"))
        cleanup_group(custody)
        require(not group_members(custody), "Command group is not absent")
        custody["verifiedAbsent"] = True
        save(path, custody)


def actual_start_utc(start_ticks):
    boot_seconds = next(int(line.split()[1]) for line in Path("/proc/stat").read_text(encoding="ascii").splitlines()
                        if line.startswith("btime "))
    return datetime.fromtimestamp(boot_seconds + start_ticks / os.sysconf("SC_CLK_TCK"), timezone.utc).isoformat()


def command(root, argv, evidence, name, timeout):
    settle_command_groups(evidence)
    environment = os.environ.copy()
    environment["GITHUB_ACTIONS"] = "false"
    environment["DOTNET_CLI_UI_LANGUAGE"] = "en"
    environment["DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER"] = "1"
    environment["MSBUILDDISABLENODEREUSE"] = "1"
    environment.pop("VSTestCollect", None)
    environment.pop("VSTestLogger", None)
    environment["VSTestResultsDirectory"] = str(evidence / "baseline-trx")
    ledger_path = evidence / (name + "-resource.json")
    custody = {"ownerRunId": os.environ.get("GITHUB_RUN_ID"), "ownerJob": os.environ.get("GITHUB_JOB"),
               "ownerUid": os.getuid(), "bootId": boot_id(), "purpose": name,
               "leaderPid": None, "group": None, "session": None, "started": False,
               "leaderStartTicks": None, "executable": shutil.which(argv[0]),
               "launchObservedUtc": datetime.now(timezone.utc).isoformat(),
               "leaseSeconds": timeout + 40, "verifiedAbsent": False}
    save(ledger_path, custody)  # Record pending launch before starting any child.
    with (evidence / (name + ".log")).open("w", encoding="utf-8") as stream:
        try:
            process = subprocess.Popen(argv, cwd=root, env=environment, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        except BaseException:
            custody["verifiedAbsent"] = True  # Popen failed without returning a child handle.
            save(ledger_path, custody)
            raise
        custody.update(leaderPid=process.pid, group=process.pid, session=process.pid, started=True)
        primary = None
        try:
            identity = process_identity(process.pid)
            require(identity is not None and identity["group"] == process.pid
                    and identity["session"] == process.pid and identity["uid"] == custody["ownerUid"],
                    "Cannot establish private command-session custody")
            custody["leaderStartTicks"] = identity["startTicks"]
            custody["actualStartUtc"] = actual_start_utc(identity["startTicks"])
            custody["initialMember"] = identity
            save(ledger_path, custody)
            return process.wait(timeout=timeout)
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                cleanup_group(custody, process)
                process.wait(timeout=10)
                require(not group_members(custody), "Command descendants remain")
                custody["verifiedAbsent"] = True
                custody["returnCode"] = process.returncode
                save(ledger_path, custody)
            except BaseException as cleanup:
                if primary is not None:
                    raise BaseExceptionGroup("Command and owned-session cleanup failed", [primary, cleanup])
                raise


def build(root, evidence, name):
    code = command(root, ["dotnet", "build", SOLUTION, "--configuration", "Release", "--no-restore",
                         "-t:Rebuild", "-warnaserror", "-p:UseLocalMalievDependencies=true",
                         "-p:UseSharedCompilation=false",
                         "-nologo", "-v:minimal"], evidence, name, 300)
    log = (evidence / (name + ".log")).read_text(encoding="utf-8")
    require(code == 0 and re.search(r"^\s*0 Warning\(s\)\s*$", log, re.M)
            and re.search(r"^\s*0 Error\(s\)\s*$", log, re.M),
            name + " must succeed with zero warnings and zero errors")


def guid(value):
    require(value is not None and str(uuid.UUID(value)) == value, "Noncanonical TRX GUID")
    return value


TRX_NAMESPACE = "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"
NS = {"t": TRX_NAMESPACE}
MAX_TRX_BYTES = 16 * 1024 * 1024


def one(parent, path):
    found = parent.findall(path, NS)
    require(len(found) == 1, "Expected one direct TRX element: " + path)
    return found[0]


def read_trx(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_TRX_BYTES + 1)
    require(len(raw) <= MAX_TRX_BYTES, "Baseline TRX exceeds 16 MiB")
    text = raw.decode("utf-8-sig", errors="strict")
    require("\0" not in text, "NUL bytes are forbidden in UTF-8 TRX")
    require(re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I) is None,
            "DTD and entity declarations are forbidden")
    declaration = re.match(r"""\s*<\?xml\b[^?]*\bencoding\s*=\s*(['"])([^'"]+)\1""", text)
    require(declaration is None or declaration.group(2).lower() == "utf-8", "TRX must declare UTF-8")
    doc = ET.fromstring(text)
    prefix = "{" + TRX_NAMESPACE + "}"
    require(doc.tag == prefix + "TestRun", "Wrong TRX root or namespace")
    require(all(isinstance(item.tag, str) and item.tag.startswith(prefix) for item in doc.iter()),
            "Foreign or unnamespaced TRX element")
    return doc, digest(raw)


def binder_failure(message, stack, category, expected_failure):
    expected_outer = (category["outerType"] + " : The JSON value could not be converted to "
                      + category["outerTarget"] + ". Path: " + category["propertyPath"]
                      + " | LineNumber: 0 | BytePositionInLine: " + str(expected_failure["bytePosition"]) + ".")
    expected_inner = ("---- " + category["innerType"]
                      + " : Cannot get the value of a token type '" + expected_failure["tokenType"] + "' as a string.")
    require(message.splitlines() == [expected_outer, expected_inner],
            "Failure differs from the exact witnessed request/string-token exception chain")
    for method in category["requiredFrames"]:
        pattern = (r"^[ \t]*at[ \t]+" + re.escape(method)
                   + r"\([^()\r\n]*\)(?:[ \t]+in[ \t]+[^\r\n]+:line[ \t]+[0-9]+)?[ \t]*$")
        require(any(re.fullmatch(pattern, line) for line in stack.splitlines()),
                "Missing exact binder/test stack frame")


def verify_fail_notices(summary, failures):
    def escaped(name):
        return name.replace("\r", r"\r").replace("\n", r"\n").replace("\t", r"\t").replace("\0", r"\0")

    expected = {escaped(item["name"]): item["name"] for item in failures}
    require(len(expected) == 5, "Expected five distinct escaped failure names")
    notices = one(summary, "./t:RunInfos")
    require(len(notices) == 5, "Expected five reporter failure notices")
    observed = set()
    for info in notices:
        require(info.tag == "{" + TRX_NAMESPACE + "}RunInfo" and info.get("outcome") == "Error"
                and len(info) == 1, "Unexpected RunInfo category or child")
        text_node = one(info, "./t:Text")
        require(len(text_node) == 0, "Nested RunInfo text")
        text = text_node.text or ""
        match = re.fullmatch(r"\[xUnit\.net [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{2}\]     (.*) \[FAIL\]", text)
        require(match is not None and match.group(1) in expected and match.group(1) not in observed,
                "Unknown, duplicated or malformed reporter failure notice")
        observed.add(match.group(1))
    require(observed == set(expected), "Reporter failures do not biject with validated failed rows")


def verify_trx(root, contract):
    reports = []
    for path in root.rglob("*.trx"):
        reports.append(path)
        if len(reports) > 1:
            break
    require(len(reports) == 1, "Exactly one isolated baseline TRX required")
    doc, trx_sha = read_trx(reports[0])
    for element, expected_count in (("ResultSummary", 1), ("Counters", 1), ("RunInfo", 5),
                                    ("UnitTest", 9), ("TestEntry", 9), ("UnitTestResult", 9)):
        require(len(doc.findall(".//t:" + element, NS)) == expected_count,
                "Unexpected global TRX element count: " + element)
    summary = one(doc, "./t:ResultSummary")
    counters = one(summary, "./t:Counters")
    for key, expected in contract["expectedCounters"].items():
        require(int(counters.get(key, "-1")) == expected, "Unexpected baseline counter: " + key)
    require(summary.get("outcome") == "Failed", "Expected RED summary missing")
    containers = [one(doc, "./t:" + name) for name in ("TestDefinitions", "TestEntries", "Results")]
    for container, child in zip(containers, ("UnitTest", "TestEntry", "UnitTestResult")):
        require(all(item.tag == "{" + TRX_NAMESPACE + "}" + child for item in container),
                "Unexpected direct TRX container child")
    definitions, entries, results = map(list, containers)
    require(len(definitions) == len(entries) == len(results) == 9, "Baseline identity cardinality")
    expected = {case["name"]: case["outcome"] for case in contract["cases"]}
    expected_cases = {case["name"]: case for case in contract["cases"]}
    require(len(expected) == 9, "Baseline roster must have nine distinct exact names")
    defs = {guid(item.get("id")): item for item in definitions}
    joins = {guid(item.get("testId")): guid(item.get("executionId")) for item in entries}
    require(len(defs) == len(joins) == 9, "Duplicate baseline definitions/entries")
    actual, executions, failures = set(), set(), []
    for result in results:
        name, test_id, execution = result.get("testName"), guid(result.get("testId")), guid(result.get("executionId"))
        require(name in expected and name not in actual and execution not in executions, "Unexpected or duplicate case")
        definition = defs.get(test_id)
        require(definition is not None and definition.get("name") == name, "Unjoined definition/name")
        defined_execution = one(definition, "./t:Execution")
        require(defined_execution.get("id") == execution and joins.get(test_id) == execution,
                "Definition/result/entry execution mismatch")
        method = one(definition, "./t:TestMethod")
        require(method.get("className", "").split(",")[0] == contract["className"]
                and method.get("name") == contract["methodName"], "Wrong test class/method")
        require(result.get("outcome") == expected[name], "Wrong outcome for exact baseline case")
        outputs = result.findall("./t:Output", NS)
        require(len(outputs) <= 1, "Duplicate result Output")
        errors = result.findall("./t:Output/t:ErrorInfo", NS)
        if expected[name] == "Failed":
            require(len(errors) == 1, "Expected one direct binder error")
            message_node, stack_node = one(errors[0], "./t:Message"), one(errors[0], "./t:StackTrace")
            require(len(message_node) == len(stack_node) == 0, "Nested failure text is forbidden")
            category = contract["failureCategory"]
            binder_failure(message_node.text or "", stack_node.text or "", category, expected_cases[name]["bindingFailure"])
            failures.append({"name": name, "testId": test_id, "executionId": execution,
                             "category": category["outerType"]})
        else:
            require(not errors, "Passing string/null control contains an error")
        actual.add(name)
        executions.add(execution)
    require(actual == set(expected), "Incomplete baseline identity set")
    require(len(doc.findall(".//t:ErrorInfo", NS)) == 5, "Additional error evidence is forbidden")
    verify_fail_notices(summary, failures)  # Only after every row, exception and frame passed.
    return {"executed": 9, "passed": 4, "failed": 5, "strictIdentityAndExecutionJoins": True,
            "exactExpectedReporterNotices": 5,
            "expectedBindingFailures": failures, "trxSha256": trx_sha,
            "historicalRuntimeOrCoverageAcceptance": False}


def run_red(root, contract, contract_bytes, evidence):
    require(not evidence.exists(), "Use fresh isolated RED evidence directory")
    evidence.mkdir(parents=True)
    require(not git(root, "status", "--porcelain", "--untracked-files=no").strip(), "Candidate checkout not clean")
    sources = candidate_sources(root, contract)
    for relative, data in sources.items():
        require(safe_path(root, relative).read_bytes() == data, "Working source differs from HEAD")
    head = git(root, "rev-parse", "HEAD").decode().strip()
    baseline = contract["baseline"]
    original = safe_path(root, baseline["programArtifact"]).read_bytes()
    require(original == git(root, "show", "HEAD:" + baseline["programArtifact"]), "Baseline asset changed")
    framed = b"blob " + str(len(original)).encode() + b"\0" + original
    require(digest(original) == baseline["programSha256"]
            and hashlib.sha1(framed).hexdigest() == baseline["programBlob"], "Baseline Program binding mismatch")
    save(evidence / "source-receipt.json", {"head": head, "contractSha256": digest(contract_bytes),
                                          "candidate": contract["candidateBindings"], "baseline": baseline})
    primary = None
    try:
        safe_path(root, baseline["programPath"]).write_bytes(original)
        safe_path(root, baseline["absentPath"]).unlink()
        build(root, evidence, "baseline-build")
        code = command(root, ["dotnet", "test", PROJECT, "--configuration", "Release", "--no-build", "--no-restore",
                              "-p:UseLocalMalievDependencies=true", "--filter", contract["filter"],
                              "--logger", "trx;LogFileName=baseline.trx",
                              "--results-directory", str(evidence / "baseline-trx")],
                       evidence, "baseline-test", 180)
        require(code == 1, "RED needs the test-failure exit, not success/arbitrary nonzero")
        proof = verify_trx(evidence / "baseline-trx", contract)
        save(evidence / "baseline-proof.json", {"head": head, **proof})
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            restore(root, contract, sources, evidence, head)
        except BaseException as cleanup:
            if primary is not None:
                raise BaseExceptionGroup("RED control and restoration both failed", [primary, cleanup])
            raise


def rebuild_candidate(root, contract, evidence):
    require(evidence.is_dir(), "No RED receipt directory")
    receipt = json.loads((evidence / "source-receipt.json").read_text(encoding="utf-8"))
    sources = candidate_sources(root, contract)
    restore(root, contract, sources, evidence, receipt["head"])
    build(root, evidence, "candidate-rebuild")
    save(evidence / "candidate-rebuild-proof.json", {"head": receipt["head"], "zeroWarnings": True,
                                                   "zeroErrors": True, "sourceRestored": True})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("run", "rebuild"))
    args = parser.parse_args()
    root, contract, contract_bytes = hosted_context()
    evidence = root / "po-header-red-control-results"
    if args.mode == "run":
        run_red(root, contract, contract_bytes, evidence)
    else:
        rebuild_candidate(root, contract, evidence)


if __name__ == "__main__":
    main()
