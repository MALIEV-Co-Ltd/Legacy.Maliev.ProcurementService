"""Fail closed on incomplete, unknown-field, or privacy-unsafe containment receipts."""
import datetime
import collections
import json
import pathlib
import re
import sys
import uuid
import xml.etree.ElementTree as ET


def native_cases(root):
    manifest = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs/procurement-fixture-containment-cases.json").read_text())
    reviewed = {(case["name"], case["id"]) for case in manifest["cases"]}
    if manifest["expectedCases"] != 18 or len(manifest["cases"]) != 18 or len(reviewed) != 18:
        raise ValueError("Frozen focused execution roster must contain exactly 18 identities")
    lifetime = "Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementFixtureLifetimeTests."
    provider_class = "Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementFixtureProviderContainmentTests."
    expected = {lifetime + name: count for name, count in {
        "CleanupFailure_StillAttemptsAllFourOwnedReleases": 4,
        "MultipleCleanupFailures_RetainEveryOriginalException": 1,
        "SuccessfulCleanup_ReleasesAllAndLeavesNoPendingHandles": 1,
        "SetupFailure_PreservesPrimaryAndRunsCleanup": 1,
        "SetupAndCleanupFailures_RetainPrimaryAndBothCleanupErrors": 1,
        "SynchronousSetupFailure_StillRunsCleanup": 1,
        "InitializationDeadline_CancelsCooperatingWorkAndCleansUp": 1,
        "CleanupTimeout_AttemptsNextReleaseAndRetainsUnfinishedHandleAndLateFault": 1,
        "SetupThatIgnoresCancellation_IsReportedUnsettledAfterBoundedCleanup": 1,
        "SuccessfulSetup_DoesNotInvokeFailureCleanup": 1,
        "CancellationCallbackFailure_DoesNotLosePrimaryOrSkipCleanup": 1,
        "ContainerPolicy_BoundsMemoryCpuLoopbackAndPreservesPostgresArguments": 1,
    }.items()}
    expected.update({provider_class + "ForcedExpiry_StopsSignalIgnoringOwnedChild": 1,
                     provider_class + "OwnedProviderBoundsAndNaturalCleanup_AreObserved": 2})
    reports = list(root.rglob("*.trx"))
    if len(reports) != 1:
        raise ValueError("Exactly one separate focused TRX required")
    document = ET.parse(reports[0])
    summaries = document.findall("./{*}ResultSummary")
    if len(document.findall(".//{*}ResultSummary")) != 1:
        raise ValueError("Exactly one direct root summary required")
    if len(summaries) != 1 or summaries[0].get("outcome") != "Completed" or document.findall(".//{*}RunInfo") or document.findall(".//{*}ErrorInfo"):
        raise ValueError("One completed summary without run/error evidence required")
    all_counters = document.findall(".//{*}Counters")
    if len(all_counters) != 1:
        raise ValueError("Exactly one focused counter block required")
    direct_counters = summaries[0].findall("./{*}Counters")
    if len(direct_counters) != 1 or direct_counters[0] is not all_counters[0]:
        raise ValueError("Counters must be the sole direct child block of the completed summary")
    counters = direct_counters[0]
    if counters is None or any(int(counters.get(key, "-1")) != 18 for key in ("total", "executed", "passed")):
        raise ValueError("Exactly 18 passing focused executions required")
    nonpassing = "failed error timeout aborted inconclusive passedButRunAborted notRunnable notExecuted disconnected warning completed inProgress pending".split()
    if set(counters.attrib) != set(nonpassing) | {"total", "executed", "passed"}:
        raise ValueError("All sixteen focused counters required without extra fields")
    if any(int(counters.get(key, "-1")) != 0 for key in nonpassing) or document.findall(".//{*}ErrorInfo"):
        raise ValueError("No failed/skipped/error focused cases allowed")
    def direct_rows(parent, child):
        parents = document.findall("./{*}" + parent)
        if len(parents) != 1 or len(document.findall(".//{*}" + parent)) != 1:
            raise ValueError("Exactly one direct focused " + parent + " container required")
        rows = parents[0].findall("./{*}" + child)
        if len(document.findall(".//{*}" + child)) != len(rows):
            raise ValueError("Focused rows must have the reviewed direct parents")
        return rows
    definitions = direct_rows("TestDefinitions", "UnitTest")
    entries = direct_rows("TestEntries", "TestEntry")
    results = direct_rows("Results", "UnitTestResult")
    defs = {row.get("id"): row for row in definitions}
    joins = {row.get("testId"): row.get("executionId") for row in entries}
    if any(len(rows) != 18 for rows in (definitions, entries, results, defs, joins)):
        raise ValueError("Focused definition/entry/result cardinality differs")
    actual, identities, executions, names = collections.Counter(), set(), set(), set()
    for row in results:
        test_id, execution = row.get("testId"), row.get("executionId")
        if str(uuid.UUID(test_id or "")) != test_id or str(uuid.UUID(execution or "")) != execution:
            raise ValueError("Focused identities must be canonical GUIDs")
        definition = defs.get(test_id)
        if definition is None or test_id in identities or execution in executions:
            raise ValueError("Duplicate or unbound focused execution")
        methods = definition.findall("./{*}TestMethod")
        bindings = definition.findall("./{*}Execution")
        if len(methods) != 1 or len(bindings) != 1 or len(definition.findall(".//{*}TestMethod")) != 1 or len(definition.findall(".//{*}Execution")) != 1:
            raise ValueError("Exactly one direct method and execution per focused definition required")
        method, bound = methods[0], bindings[0]
        if method is None or bound is None or bound.get("id") != execution or joins.get(test_id) != execution or row.get("outcome") != "Passed" or definition.get("name") != row.get("testName"):
            raise ValueError("Focused result/definition/entry join differs")
        codebase = method.get("codeBase", "").replace("\\", "/")
        expected_suffix = "/Legacy.Maliev.ProcurementService.Tests/bin/Release/net10.0/Legacy.Maliev.ProcurementService.Tests.dll"
        if not codebase.endswith(expected_suffix) or definition.get("storage", "").replace("\\", "/").lower() != codebase.lower() or method.get("adapterTypeName") != "executor://xunit/VsTestRunner3/netcore/":
            raise ValueError("Focused DLL/adapter custody differs")
        actual[method.get("className", "") + "." + method.get("name", "")] += 1
        identities.add(test_id); executions.add(execution)
        names.add((row.get("testName"), test_id))
    if dict(actual) != expected or names != reviewed:
        raise ValueError("Focused method executions differ from authored 15+3 roster")


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise ValueError("Receipt fields differ from the reviewed privacy-safe schema")


def guid(value):
    if not isinstance(value, str) or uuid.UUID(value).hex != value:
        raise ValueError("Run identity must be a canonical compact GUID")


def timestamp(value):
    result = datetime.datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Receipt time requires an explicit timezone")
    return result


def provider(value, scenario, parent):
    exact(value, "Scenario ResourceRunId Owner ObservedAtUtc CompletedAtUtc Resources ContainersAbsent VolumesAbsent CleanupObserved UnsettledOperations ObservedOperationFailureTypes DestructiveObserverActions PersistentData")
    guid(value["ResourceRunId"])
    if value["Scenario"] != scenario or value["Owner"] != "procurement-runtime-fixture":
        raise ValueError("Provider identity differs")
    expected_failures = ["System.IO.IOException"] if scenario == "partial-setup-failure" else []
    if value["CleanupObserved"] is not True or value["PersistentData"] is not False or value["UnsettledOperations"] != 0 or value["DestructiveObserverActions"] != 0 or value["ObservedOperationFailureTypes"] != expected_failures:
        raise ValueError("Provider cleanup is not proven")
    if timestamp(value["CompletedAtUtc"]) < timestamp(value["ObservedAtUtc"]) or len(value["Resources"]) != 2:
        raise ValueError("Provider timing or cardinality differs")
    ids, volumes, roles = set(), set(), set()
    for row in value["Resources"]:
        exact(row, "Id Role Created StartedAt ProcessId MemoryBytes MemorySwapBytes NanoCpus Entrypoint Command Labels HostIps Volumes")
        if any(not isinstance(row[key], str) or not re.fullmatch(r"[0-9T:./ +Z-]+", row[key]) for key in ("Created", "StartedAt")):
            raise ValueError("Unsafe provider timestamp value")
        if not re.fullmatch(r"[a-f0-9]{64}", row["Id"]) or row["Id"] in ids:
            raise ValueError("Container identity differs")
        ids.add(row["Id"]); roles.add(row["Role"])
        if row["MemoryBytes"] != 1073741824 or row["MemorySwapBytes"] != 1073741824 or row["NanoCpus"] != 750000000 or row["ProcessId"] <= 0:
            raise ValueError("Actual provider bounds differ")
        if row["Entrypoint"] != ["sh", "-c", 'exec timeout --signal=INT --kill-after=10s 1800 docker-entrypoint.sh "$@"', "procurement-owned-fixture"]:
            raise ValueError("Actual hard-expiry command differs")
        if row["Command"] != ["-c", "fsync=off", "-c", "full_page_writes=off", "-c", "synchronous_commit=off"]:
            raise ValueError("PostgreSQL builder arguments changed")
        if not row["HostIps"] or set(row["HostIps"]) != {"127.0.0.1"} or not row["Volumes"]:
            raise ValueError("Actual binding or volume observation missing")
        labels = row["Labels"]
        exact(labels, "maliev.codex.owner maliev.codex.run maliev.codex.parent-run maliev.codex.role maliev.codex.expires-utc maliev.codex.persistent-data org.testcontainers.session-id")
        if labels["maliev.codex.run"] != value["ResourceRunId"] or labels["maliev.codex.parent-run"] != parent or labels["maliev.codex.owner"] != value["Owner"] or labels["maliev.codex.role"] != row["Role"] or labels["maliev.codex.persistent-data"] != "false":
            raise ValueError("Ownership differs")
        guid(labels["org.testcontainers.session-id"].replace("-", ""))
        if timestamp(labels["maliev.codex.expires-utc"]) <= timestamp(value["ObservedAtUtc"]):
            raise ValueError("Provider ownership lease expired before observation")
        for volume in row["Volumes"]:
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", volume):
                raise ValueError("Unsafe volume identity")
            volumes.add(volume)
    if roles != {"supplier", "purchase-order"} or len(value["ContainersAbsent"]) != 2 or set(value["ContainersAbsent"]) != ids or len(value["VolumesAbsent"]) != len(volumes) or set(value["VolumesAbsent"]) != volumes:
        raise ValueError("Owned resource absence is incomplete")
    return ids, volumes


def verify(root):
    native_cases(root)
    outer = json.loads((root / "outer-process-cleanup.json").read_text())
    exact(outer, "schemaVersion observationContract runId startedAtUtc completedAtUtc launchProcess expectedTestExecutable testProcess testExitCode observedProcesses observedResources ownedContainers ownedVolumes sessions remaining errorTypes commandFailures destructiveDockerActions")
    guid(outer["runId"])
    if not isinstance(outer["commandFailures"], list): raise ValueError("Command failure custody must be a list")
    for failure in outer["commandFailures"]:
        exact(failure, "query containerId exitCode category stderrBytes stderrSha256 phase commandLaunchProcess durationMilliseconds childTerminalObserved streamsClosed handleClosed")
        if failure["phase"] not in ("native-observation", "cleanup-observation", "not-started") or type(failure["durationMilliseconds"]) is not int or failure["durationMilliseconds"] < 0 or any(type(failure[key]) is not bool for key in ("childTerminalObserved", "streamsClosed", "handleClosed")):
            raise ValueError("Invalid command phase or cleanup custody")
        process = failure["commandLaunchProcess"]
        exact(process, "pid startTicks group session executable")
        if any(type(process[key]) is not int or process[key] <= 0 for key in ("pid", "startTicks", "group", "session")) or not isinstance(process["executable"], str) or not process["executable"].startswith("/"):
            raise ValueError("Invalid command launch identity")
        if failure["query"] not in ("inspect-container", "list-containers", "list-volumes", "unknown-query") or failure["category"] not in ("exact-container-not-found", "unclassified-command-failure"):
            raise ValueError("Unknown command failure category")
        if failure["containerId"] is not None and not re.fullmatch(r"[a-f0-9]{12,64}", failure["containerId"]): raise ValueError("Unsafe failure target")
        if type(failure["exitCode"]) is not int or failure["exitCode"] == 0 or type(failure["stderrBytes"]) is not int or not 0 <= failure["stderrBytes"] <= 65536 or not re.fullmatch(r"[a-f0-9]{64}", failure["stderrSha256"]):
            raise ValueError("Invalid bounded command failure custody")
    if outer["commandFailures"]: raise ValueError("Any failed observation prevents qualification")
    if outer["schemaVersion"] != 2 or outer["observationContract"] != "one-running-snapshot-full-id-census-v1" or outer["testExitCode"] != 0 or outer["remaining"] or outer["errorTypes"] or outer["destructiveDockerActions"] != 0 or not outer["sessions"]:
        raise ValueError("Independent cleanup witness failed")
    if timestamp(outer["completedAtUtc"]) < timestamp(outer["startedAtUtc"]):
        raise ValueError("Outer timing differs")
    for process in outer["observedProcesses"]:
        exact(process, "pid startTicks group session executable")
        if any(type(process[key]) is not int or process[key] <= 0 for key in ("pid", "startTicks", "group", "session")) or not isinstance(process["executable"], str) or not process["executable"].startswith("/"):
            raise ValueError("Process identity missing")
    launch, native, expected = outer["launchProcess"], outer["testProcess"], outer["expectedTestExecutable"]
    if launch not in outer["observedProcesses"] or native not in outer["observedProcesses"]:
        raise ValueError("Both immutable launch and native execution identities must be observed")
    if not isinstance(expected, str) or not expected.startswith("/") or pathlib.PurePosixPath(expected).name != "dotnet" or native["executable"] != expected:
        raise ValueError("Expected authorized dotnet executable transition not proven")
    if any(launch[key] != native[key] for key in ("pid", "startTicks", "group", "session")) or launch["pid"] != launch["group"] or launch["pid"] != launch["session"]:
        raise ValueError("Launch/native birth group session changed")
    if outer["testProcess"] not in outer["observedProcesses"]:
        raise ValueError("Original test process custody missing")
    if not outer["ownedContainers"] or any(not re.fullmatch(r"[a-f0-9]{64}", identity) for identity in outer["ownedContainers"]):
        raise ValueError("Unsafe or missing outer container identity")
    if any(not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", identity) for identity in outer["ownedVolumes"]):
        raise ValueError("Unsafe outer volume identity")
    for session in outer["sessions"]:
        guid(session.replace("-", ""))
    resource_rows = {}
    for row in outer["observedResources"]:
        exact(row, "id role resourceRunId parentRunId createdAt startedAt processId memoryBytes memorySwapBytes nanoCpus expiresAt volumes hostIps")
        guid(row["resourceRunId"])
        if row["parentRunId"] != outer["runId"] or row["id"] in resource_rows or row["processId"] <= 0:
            raise ValueError("Independent running resource identity differs")
        forced = row["role"] == "forced-expiry-control"
        memory = 67108864 if forced else 1073741824
        cpu = 100000000 if forced else 750000000
        binding_matches = row["hostIps"] == [] if forced else set(row["hostIps"]) == {"127.0.0.1"}
        if row["role"] not in ("supplier", "purchase-order", "forced-expiry-control") or row["memoryBytes"] != memory or row["memorySwapBytes"] != memory or row["nanoCpus"] != cpu or not binding_matches:
            raise ValueError("Independent actual role, limits, or loopback binding differ")
        if timestamp(row["startedAt"]) < timestamp(row["createdAt"]) or timestamp(row["expiresAt"]) <= timestamp(row["startedAt"]):
            raise ValueError("Independent provider timing or finite lease differs")
        resource_rows[row["id"]] = row
    if set(resource_rows) != set(outer["ownedContainers"]):
        raise ValueError("Independent running observation missing for an owned container")
    observed_ids, observed_volumes, observed_runs = set(), set(), set()
    for name in ("successful-lifecycle", "partial-setup-failure"):
        value = json.loads((root / "fixture-containment" / (name + ".json")).read_text())
        ids, volumes = provider(value, name, outer["runId"])
        if observed_ids & ids or observed_volumes & volumes or value["ResourceRunId"] in observed_runs:
            raise ValueError("Distinct provider scenarios reused an owned resource identity")
        observed_ids.update(ids); observed_volumes.update(volumes); observed_runs.add(value["ResourceRunId"])
        if not ids <= set(outer["ownedContainers"]) or not volumes <= set(outer["ownedVolumes"]):
            raise ValueError("Outer witness missed owned provider resources")
        for row in value["Resources"]:
            actual = resource_rows[row["Id"]]
            if actual["resourceRunId"] != value["ResourceRunId"] or actual["role"] != row["Role"] or set(actual["volumes"]) != set(row["Volumes"]):
                raise ValueError("Independent provider run, role, or volume custody differs")
    expiry = json.loads((root / "fixture-containment/forced-expiry.json").read_text())
    exact(expiry, "Scenario ResourceRunId ContainerId ParentRunId Owner Volumes VolumesAbsent ExpiredBeforeCleanup ExitCode ElapsedSeconds ContainerAbsent UnsettledOperations ObservedOperationFailureTypes PersistentData")
    guid(expiry["ResourceRunId"])
    if expiry["Scenario"] != "forced-expiry" or not re.fullmatch(r"[a-f0-9]{64}", expiry["ContainerId"]) or expiry["ExpiredBeforeCleanup"] is not True or expiry["ContainerAbsent"] is not True or expiry["ExitCode"] != 137 or not 2 <= expiry["ElapsedSeconds"] <= 15 or expiry["UnsettledOperations"] != 0 or expiry["ObservedOperationFailureTypes"] or expiry["PersistentData"] is not False:
        raise ValueError("Actual forced expiry is not proven")
    if expiry["ParentRunId"] != outer["runId"] or expiry["Owner"] != "procurement-runtime-fixture" or expiry["ContainerId"] not in outer["ownedContainers"] or not expiry["Volumes"] or len(expiry["VolumesAbsent"]) != len(set(expiry["Volumes"])) or set(expiry["VolumesAbsent"]) != set(expiry["Volumes"]) or not set(expiry["Volumes"]) <= set(outer["ownedVolumes"]):
        raise ValueError("Independent expiry-control ownership and volume absence are incomplete")
    if expiry["ContainerId"] in observed_ids or expiry["ResourceRunId"] in observed_runs or set(expiry["Volumes"]) & observed_volumes:
        raise ValueError("Expiry control reused a provider identity")
    actual_expiry = resource_rows[expiry["ContainerId"]]
    if actual_expiry["resourceRunId"] != expiry["ResourceRunId"] or actual_expiry["role"] != "forced-expiry-control" or set(actual_expiry["volumes"]) != set(expiry["Volumes"]):
        raise ValueError("Independent expiry-control running identity differs")
    if set(outer["ownedContainers"]) != observed_ids | {expiry["ContainerId"]} or set(outer["ownedVolumes"]) != observed_volumes | set(expiry["Volumes"]):
        raise ValueError("Unknown owned resources appeared outside the three reviewed scenarios")
    return {"providerScenarios": 3, "independentCleanup": True, "focusedPassed": 18,
            "fullSuiteAcceptance": False, "productionQualification": False}


if __name__ == "__main__":
    print(json.dumps(verify(pathlib.Path(sys.argv[1]))))
