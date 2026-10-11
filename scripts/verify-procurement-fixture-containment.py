"""Fail closed on incomplete, unknown-field, or privacy-unsafe containment receipts."""
import datetime
import collections
import json
import pathlib
import re
import sys
import uuid
import subprocess
import hashlib
import os

def finite_activation(extension):
    if not extension["enabled"]: return []
    if extension.get("reviewedProducer") is None or len(extension.get("cases",[])) != 5:
        raise ValueError("Finite extension requires reviewed actual producer and native IDs")
    current = subprocess.check_output(["git","-C",str(pathlib.Path(__file__).resolve().parents[1]),"rev-parse","HEAD"],timeout=10,text=True).strip()
    declared=os.environ.get("MALIEV_FINITE_OWNER_SOURCE_HEAD")
    if not isinstance(declared,str) or not re.fullmatch(r"[a-f0-9]{40}",declared): raise ValueError("Trusted original CI source head missing")
    # Producer is the implementation commit; the subsequent reviewed binding commit may differ.
    ancestry=subprocess.run(["git","-C",str(pathlib.Path(__file__).resolve().parents[1]),"merge-base","--is-ancestor",extension["reviewedProducer"],current],capture_output=True,timeout=10)
    if ancestry.returncode: raise ValueError("Reviewed implementation producer ancestry unavailable")
    binding=json.loads((pathlib.Path(__file__).resolve().parents[1]/"docs/procurement-finite-owner-source-binding.json").read_text())
    if binding["reviewedProducer"] != extension["reviewedProducer"] or binding["releaseAllowed"] is not True: raise ValueError("Finite source binding not reviewed")
    for pin in binding["inputs"]:
        path=pathlib.Path(__file__).resolve().parents[1]/pin["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=pin["sha256"]: raise ValueError("Finite source input drift")
    # Original automatic CI API/artifact custody must independently bind declared source head
    # and actual merge HEAD; matching a local environment field alone is not acceptance.
    for case in extension["cases"]:
        if str(uuid.UUID(case.get("id") or "")) != case["id"]: raise ValueError("Finite native ID unreviewed")
    return extension["cases"]

def finite_bootstrap(extension):
    if extension.get("discoveryOnly") is not True or extension["enabled"]:
        raise ValueError("Explicit inactive discovery mode required")
    if os.environ.get("MALIEV_FINITE_OWNER_DISCOVERY") != "reviewed-source-only":
        raise ValueError("Existing reviewed workflow discovery declaration required")
    source_root = pathlib.Path(__file__).resolve().parents[1]
    binding = json.loads((source_root / "docs/procurement-finite-owner-source-binding.json").read_text())
    producer = binding.get("bootstrapReviewedProducer")
    if binding.get("bootstrapSourceAdmission") is not True or not isinstance(producer, str) or not re.fullmatch(r"[a-f0-9]{40}", producer):
        raise ValueError("Real source producer and explicit source admission not reviewed")
    if binding["releaseAllowed"] is not False or binding["reviewedProducer"] is not None or binding["nativeIds"] is not None:
        raise ValueError("Discovery cannot be final acceptance")
    declared = os.environ.get("MALIEV_FINITE_OWNER_SOURCE_HEAD")
    if not isinstance(declared, str) or not re.fullmatch(r"[a-f0-9]{40}", declared):
        raise ValueError("Original CI source head missing")
    for revision in [producer, declared]:
        ancestry = subprocess.run(["git", "-C", str(source_root), "merge-base", "--is-ancestor", revision, "HEAD"], capture_output=True, timeout=10)
        if ancestry.returncode: raise ValueError("Actual source ancestry unavailable")
    for pin in binding["inputs"]:
        if hashlib.sha256((source_root / pin["path"]).read_bytes()).hexdigest() != pin["sha256"]:
            raise ValueError("Discovery source pin drift")
        original = subprocess.check_output(["git", "-C", str(source_root), "show", producer + ":" + pin["path"]], timeout=10)
        blob = subprocess.check_output(["git", "-C", str(source_root), "rev-parse", producer + ":" + pin["path"]], timeout=10, text=True).strip()
        if hashlib.sha256(original).hexdigest() != pin["sha256"] or blob != pin["proposedGitBlob"]:
            raise ValueError("Actual reviewed producer Git bytes differ")
    if len(extension["cases"]) != 5 or any(case["id"] is not None for case in extension["cases"]):
        raise ValueError("Discovery IDs must remain unqualified")
    return extension["cases"]

def finite_receipt(value, observation, outer):
    required="Scenario Profile Image ImageId ImageDigests Launcher ResourceRunId ContainerId ParentRunId Owner ScopeCaptured Volumes VolumesAbsent Acquired Running StoppedBeforeCleanup LauncherExpiryCandidate OwnerWatchdogInvoked StoppedByOwner OwnerActions FiniteLifecycleOwnerCleanupObserved FiniteLifecycleQualified ExternalTerminationExcluded NaturalExpiryProven ExitCode ElapsedSeconds ContainerAbsent PublicationSnapshotPendingCount PayloadWrittenBeforePublicationCompletion ObservedOperationFailureTypes PersistentData"
    exact(value,required)
    if observation.get("acquisitionEligible") is not True or value["ScopeCaptured"] is not True:
        raise ValueError("Refused or absent original custody is ineligible")
    if value["FiniteLifecycleQualified"] is not False or value["NaturalExpiryProven"] is not False or value["ExternalTerminationExcluded"] is not False:
        raise ValueError("Owner cannot self-qualify or claim natural causality")
    if value["ContainerId"] != observation["id"] or value["ParentRunId"] != outer["runId"] or value["ResourceRunId"] != observation["resourceRunId"] or value["Owner"] != "procurement-runtime-fixture":
        raise ValueError("Finite independent identity join differs")
    lifecycle_fields="ObservedAtUtc ObservedTicks ContainerId ImageId CreatedAt StartedAt FinishedAt ProcessId Running OomKilled ExitCode MemoryBytes MemorySwapBytes NanoCpus Entrypoint Command Labels Mounts Bindings"
    for phase in ["Acquired","Running"]:
        exact(value[phase],lifecycle_fields)
        row=value[phase]
        if timestamp(row["ObservedAtUtc"])<timestamp(row["CreatedAt"]): raise ValueError("Finite observation before creation")
        if phase=="Running" and (row["Running"] is not True or timestamp(row["ObservedAtUtc"])<timestamp(row["StartedAt"])): raise ValueError("Finite running observation before birth")
    scope=observation["finiteOwnerProfileScope"]
    exact(scope,"imageId entrypoint command mounts labels hostBindings")
    profile=value["Profile"]
    if profile not in ("bookworm","alpine") or value["Scenario"]!="expiry-profile-"+profile or value["Image"]!="postgres:18.1-"+profile:
        raise ValueError("Unknown finite image profile")
    launcher='exec timeout --signal=INT --kill-after=1s 2 "$@"' if profile=="bookworm" else 'exec /bin/busybox timeout -s INT -k 1 2 "$@"'
    command=["sh","-c",'trap "" INT TERM; while :; do sleep 1; done']
    if value["Launcher"]!=launcher or scope["entrypoint"]!=["sh","-c",launcher,"procurement-expiry-profile"] or scope["command"]!=command:
        raise ValueError("Finite fixed launcher/workload differs")
    ports=scope["hostBindings"]
    if set(ports)!={"5432/tcp"} or len(ports["5432/tcp"])!=1:
        raise ValueError("Finite single port missing")
    port=ports["5432/tcp"][0]
    if port["HostIp"]!="127.0.0.1" or not re.fullmatch(r"[0-9]{1,5}",port["HostPort"]) or not 1<=int(port["HostPort"])<=65535:
        raise ValueError("Finite port differs")
    if value["ImageId"] != scope["imageId"] or value["Running"]["Entrypoint"] != scope["entrypoint"] or value["Running"]["Command"] != scope["command"]:
        raise ValueError("Finite image/command custody differs")
    expected_mounts=sorted((m["Name"],m["Destination"],m["RW"]) for m in scope["mounts"])
    for phase in ["Acquired","Running"]:
        row=value[phase]
        if row["MemoryBytes"]!=67108864 or row["MemorySwapBytes"]!=67108864 or row["NanoCpus"]!=100000000:
            raise ValueError("Finite inspected caps differ")
        if row["ContainerId"]!=value["ContainerId"] or row["ImageId"]!=value["ImageId"] or sorted((m["Name"],m["Destination"],m["ReadWrite"]) for m in row["Mounts"])!=expected_mounts:
            raise ValueError("Original finite mounts or identity differ")
        if row["CreatedAt"] != value["Acquired"]["CreatedAt"] or row["Labels"]!=value["Acquired"]["Labels"]:
            raise ValueError("Immutable original labels/lease/birth differ")
    if value["Running"]["StartedAt"] != observation["startedAt"] or value["Running"]["ProcessId"] != observation["processId"]:
        raise ValueError("Finite observed running birth differs")
    stopped=value["StoppedByOwner"] or value["StoppedBeforeCleanup"]
    if stopped is not None:
        exact(stopped,lifecycle_fields)
        if timestamp(stopped["ObservedAtUtc"])<timestamp(stopped["FinishedAt"]): raise ValueError("Finite stopped observation before finish")
        if stopped["ContainerId"]!=value["ContainerId"] or stopped["ImageId"]!=value["ImageId"] or stopped["Entrypoint"]!=scope["entrypoint"] or stopped["Command"]!=scope["command"]:
            raise ValueError("Finite stopped identity/command drift")
        if stopped["MemoryBytes"]!=67108864 or stopped["MemorySwapBytes"]!=67108864 or stopped["NanoCpus"]!=100000000:
            raise ValueError("Finite stopped caps drift")
    if stopped is None or stopped["Running"] is not False or stopped["CreatedAt"]!=value["Acquired"]["CreatedAt"] or stopped["Labels"]!=value["Acquired"]["Labels"] or stopped["StartedAt"]!=value["Running"]["StartedAt"]:
        raise ValueError("Finite stopped birth or lease drift")
    if timestamp(value["Running"]["ObservedAtUtc"])>=timestamp(stopped["FinishedAt"]): raise ValueError("Finite running observation after stop")
    if sorted((m["Name"],m["Destination"],m["ReadWrite"]) for m in stopped["Mounts"])!=expected_mounts:
        raise ValueError("Stopped immutable volume scope drift")
    if value["Acquired"]["Labels"]!=scope["labels"]: raise ValueError("Independent labels/expiry join differs")
    if value["ContainerAbsent"] is not True or value["FiniteLifecycleOwnerCleanupObserved"] is not True or set(value["Volumes"])!=set(value["VolumesAbsent"]) or set(value["Volumes"])!=set(observation["volumes"]):
        raise ValueError("Finite original scope cleanup missing")
    if type(value["PublicationSnapshotPendingCount"]) is not int or not 0<=value["PublicationSnapshotPendingCount"]<=1 or value["PayloadWrittenBeforePublicationCompletion"] is not True or value["ObservedOperationFailureTypes"] or value["PersistentData"] is not False:
        raise ValueError("Finite publication unsettled/faulted")
    # Passed native case awaits shared cleanup and asserts actual task settlement. Existing outer
    # exact-process exit/empty census prove worker and resource absence; precompletion JSON does not.
    if outer["testExitCode"]!=0 or outer["remaining"] or outer["errorTypes"]:
        raise ValueError("No terminal native settlement/independent absence")
    if value["OwnerActions"][-1:] != ["remove-requested:"+value["ContainerId"]]:
        raise ValueError("Exact owner removal absent")
    return {"finiteOwnerLifecycleQualified":True,"naturalExpiryProven":False,"providerAdmission":False}

import xml.etree.ElementTree as ET


def native_cases(root, discovery=False):
    manifest = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs/procurement-fixture-containment-cases.json").read_text())
    extension=manifest.get("finiteOwnerExtension", {"enabled":False})
    extra=finite_bootstrap(extension) if discovery else finite_activation(extension)
    total=18+len(extra)
    reviewed = {(case["name"], case["id"]) for case in manifest["cases"] + ([] if discovery else extra)}
    expected_names = {case["name"] for case in manifest["cases"] + extra}
    if manifest["expectedCases"] != 18 or len(manifest["cases"]) != 18 or len(reviewed) != (18 if discovery else total) or len(expected_names) != total:
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
    if extra:
        expected["Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementImageExpiryProfileWitnessTests.ImageSpecificControl_HasFiniteOwnerCleanup"]=2
        expected["Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementImageExpiryProfileWitnessTests.RecoveryRead_BlockedTaskRemainsOwnedAfterDeadline"]=1
        expected["Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementImageExpiryProfileWitnessTests.RecoveryRead_PostTimeoutFaultRetainsOriginalReference"]=1
        expected["Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementImageExpiryProfileWitnessTests.RecoveryRead_ExpiredTotalLeaseRefusesFalseSettlement"]=1
    reports = list(root.rglob("*.trx"))
    if len(reports) != 1:
        raise ValueError("Exactly one separate focused TRX required")
    document = ET.parse(reports[0])
    if discovery and (document.getroot().tag.rsplit("}", 1)[-1] != "TestRun" or str(uuid.UUID(document.getroot().get("id") or "")) != document.getroot().get("id")):
        raise ValueError("Canonical original TestRun identity required for discovery")
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
    if counters is None or any(int(counters.get(key, "-1")) != total for key in ("total", "executed", "passed")):
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
    if any(len(rows) != total for rows in (definitions, entries, results, defs, joins)):
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
        display_qualified = row.get("testName", "").split("(", 1)[0]
        actual_qualified = method.get("className", "") + "." + method.get("name", "")
        if display_qualified != actual_qualified:
            raise ValueError("Per-row frozen display name/class/method mapping differs")
        actual[method.get("className", "") + "." + method.get("name", "")] += 1
        identities.add(test_id); executions.add(execution)
        names.add((row.get("testName"), test_id))
    if dict(actual) != expected or (not discovery and names != reviewed) or (discovery and (not reviewed <= names or {name for name, _ in names} != expected_names)):
        raise ValueError("Focused method executions differ from authored 15+3 roster")
    return [{"name": name, "id": test_id} for name, test_id in sorted(names) if name not in {case["name"] for case in manifest["cases"]}]


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


def verify(root, discovery=False):
    discovered = native_cases(root, discovery)
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
    if outer["schemaVersion"] != 3 or outer["observationContract"] != "one-running-snapshot-full-id-census-v2" or outer["testExitCode"] != 0 or outer["remaining"] or outer["errorTypes"] or outer["destructiveDockerActions"] != 0 or not outer["sessions"]:
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
        profile=row["role"].startswith("expiry-profile-")
        exact(row, "id role creationKind testcontainersSessionId resourceRunId parentRunId createdAt startedAt processId memoryBytes memorySwapBytes nanoCpus expiresAt volumes hostIps" + (" finiteOwnerProfileScope acquisitionEligible" if profile else ""))
        guid(row["resourceRunId"])
        if row["parentRunId"] != outer["runId"] or row["id"] in resource_rows or row["processId"] <= 0:
            raise ValueError("Independent running resource identity differs")
        forced = row["role"] == "forced-expiry-control" or profile
        if forced:
            if row["creationKind"] != "docker-api-manual" or row["testcontainersSessionId"] is not None:
                raise ValueError("Manual expiry source session applicability differs")
        else:
            if row["creationKind"] != "testcontainers" or not isinstance(row["testcontainersSessionId"], str):
                raise ValueError("Testcontainers provider session ownership missing")
            guid(row["testcontainersSessionId"].replace("-", ""))
            if row["testcontainersSessionId"] not in outer["sessions"]:
                raise ValueError("Provider session missing from independent terminal census")
        memory = 67108864 if forced else 1073741824
        cpu = 100000000 if forced else 750000000
        binding_matches = row["hostIps"] == [] if forced and not profile else set(row["hostIps"]) == {"127.0.0.1"}
        if row["role"] not in ("supplier", "purchase-order", "forced-expiry-control", "expiry-profile-bookworm", "expiry-profile-alpine") or row["memoryBytes"] != memory or row["memorySwapBytes"] != memory or row["nanoCpus"] != cpu or not binding_matches:
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
            if actual["resourceRunId"] != value["ResourceRunId"] or actual["role"] != row["Role"] or set(actual["volumes"]) != set(row["Volumes"]) or actual["testcontainersSessionId"] != row["Labels"].get("org.testcontainers.session-id"):
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
    finite_ids, finite_volumes = set(), set()
    extension=json.loads((pathlib.Path(__file__).resolve().parents[1]/"docs/procurement-fixture-containment-cases.json").read_text()).get("finiteOwnerExtension", {"enabled":False})
    if extension["enabled"] or discovery:
        for profile in ["bookworm","alpine"]:
            value=json.loads((root/"fixture-containment"/("expiry-profile-"+profile+".json")).read_text())
            if value["Profile"]!=profile or value["ContainerId"] in observed_ids|finite_ids|{expiry["ContainerId"]} or set(value["Volumes"]) & (observed_volumes|finite_volumes|set(expiry["Volumes"])):
                raise ValueError("Finite profiles reused owned scope")
            finite_receipt(value,resource_rows[value["ContainerId"]],outer)
            finite_ids.add(value["ContainerId"]);finite_volumes.update(value["Volumes"])
    if set(outer["ownedContainers"]) != observed_ids | {expiry["ContainerId"]} | finite_ids or set(outer["ownedVolumes"]) != observed_volumes | set(expiry["Volumes"]) | finite_volumes:
        raise ValueError("Unknown owned resources appeared outside the three reviewed scenarios")
    return {"providerScenarios": 3, "independentCleanup": True, "focusedPassed": 18+(5 if extension["enabled"] or discovery else 0), "finiteOwnerLifecycleProfiles":len(finite_ids),
            "fullSuiteAcceptance": False, "productionQualification": False,
            "provisionalDiscovery": discovery, "finiteExtensionQualified": extension["enabled"] and not discovery,
            "discoveredUnreviewedIdentities": discovered if discovery else []}


def source_admission(extension, lane):
    if lane == "reviewed-source-only":
        finite_bootstrap(extension)
    elif lane == "qualified-full-only":
        if len(finite_activation(extension)) != 5:
            raise ValueError("Ordinary full enrollment requires reviewed exact23 identity custody")
    else:
        raise ValueError("Unknown source admission lane")


if __name__ == "__main__":
    if sys.argv[1:] == ["--source-admission"]:
        extension = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs/procurement-fixture-containment-cases.json").read_text())["finiteOwnerExtension"]
        source_admission(extension, os.environ.get("MALIEV_FINITE_OWNER_DISCOVERY"))
        print(json.dumps({"sourceAdmissionChecked": True, "nativeExecuted": False, "qualification": False}))
        raise SystemExit(0)
    discovery = len(sys.argv) == 3 and sys.argv[2] == "--provisional-discovery"
    if len(sys.argv) > 2 and not discovery: raise ValueError("Unknown verification mode")
    root = pathlib.Path(sys.argv[1])
    result = verify(root, discovery)
    if discovery:
        payload = (json.dumps(result, indent=2) + "\n").encode()
        if len(payload) > 65536: raise ValueError("Provisional discovery payload exceeds bound")
        with (root / "provisional-discovery.json").open("xb") as stream: stream.write(payload)
        print(json.dumps(result))
        raise SystemExit(2)  # Explicit provisional evidence, never a green acceptance gate.
    print(json.dumps(result))
