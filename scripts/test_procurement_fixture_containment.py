"""Provider-free negative controls; these never qualify native resource cleanup."""
import importlib.util
import json
import pathlib
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("containment", pathlib.Path(__file__).with_name("verify-procurement-fixture-containment.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def receipt():
    run, parent = "a" * 32, "b" * 32
    rows = []
    for index, role in enumerate(("supplier", "purchase-order")):
        identity = str(index + 1) * 64
        rows.append({"Id": identity, "Role": role, "Created": "2026-10-11", "StartedAt": "2026-10-11",
                     "ProcessId": index + 1, "MemoryBytes": 1073741824, "MemorySwapBytes": 1073741824,
                     "NanoCpus": 750000000, "Entrypoint": ["sh", "-c", 'exec timeout --signal=INT --kill-after=10s 1800 docker-entrypoint.sh "$@"', "procurement-owned-fixture"],
                     "Command": ["-c", "fsync=off", "-c", "full_page_writes=off", "-c", "synchronous_commit=off"],
                     "Labels": {"maliev.codex.owner": "procurement-runtime-fixture", "maliev.codex.run": run,
                                "maliev.codex.parent-run": parent, "maliev.codex.role": role,
                                "maliev.codex.expires-utc": "2026-10-11T09:32:00+00:00", "maliev.codex.persistent-data": "false",
                                "org.testcontainers.session-id": "c" * 32},
                     "HostIps": ["127.0.0.1"], "Volumes": [identity]})
    return {"Scenario": "successful-lifecycle", "ResourceRunId": run, "Owner": "procurement-runtime-fixture",
            "ObservedAtUtc": "2026-10-11T09:00:00+00:00", "CompletedAtUtc": "2026-10-11T09:01:00+00:00",
            "Resources": rows, "ContainersAbsent": [row["Id"] for row in rows], "VolumesAbsent": [row["Volumes"][0] for row in rows],
            "CleanupObserved": True, "UnsettledOperations": 0, "ObservedOperationFailureTypes": [],
            "DestructiveObserverActions": 0, "PersistentData": False}


class ReceiptControls(unittest.TestCase):
    def test_valid_synthetic_schema_only(self):
        guard.provider(receipt(), "successful-lifecycle", "b" * 32)

    def test_expected_primary_is_retained_in_failure_scenario(self):
        value = receipt(); value["Scenario"] = "partial-setup-failure"
        value["ObservedOperationFailureTypes"] = ["System.IO.IOException"]
        guard.provider(value, value["Scenario"], "b" * 32)

    def test_unknown_fields_fail_at_every_schema_level(self):
        for level in ("root", "resource", "labels"):
            value = receipt()
            target = value if level == "root" else value["Resources"][0] if level == "resource" else value["Resources"][0]["Labels"]
            target["ConnectionString"] = "forbidden"
            with self.subTest(level=level), self.assertRaises(ValueError):
                guard.provider(value, "successful-lifecycle", "b" * 32)

    def test_missing_resource_absence_fails(self):
        for key in ("ContainersAbsent", "VolumesAbsent"):
            value = receipt(); value[key].pop()
            with self.subTest(key=key), self.assertRaises(ValueError):
                guard.provider(value, "successful-lifecycle", "b" * 32)

    def test_limits_binding_and_command_drift_fail(self):
        for field, replacement in (("MemoryBytes", 0), ("MemorySwapBytes", -1), ("NanoCpus", 0), ("HostIps", ["0.0.0.0"]), ("Entrypoint", []), ("Command", [])):
            value = receipt(); value["Resources"][0][field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                guard.provider(value, "successful-lifecycle", "b" * 32)

    def test_cleanup_failure_or_pending_handles_fail(self):
        for key, replacement in (("CleanupObserved", False), ("UnsettledOperations", 1), ("ObservedOperationFailureTypes", ["System.TimeoutException"]), ("PersistentData", True), ("DestructiveObserverActions", 1)):
            value = receipt(); value[key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError):
                guard.provider(value, "successful-lifecycle", "b" * 32)

    def test_wrong_parent_or_duplicate_identity_fails(self):
        value = receipt(); value["Resources"][1]["Id"] = value["Resources"][0]["Id"]
        with self.assertRaises(ValueError):
            guard.provider(value, "successful-lifecycle", "b" * 32)


class NativeRosterControls(unittest.TestCase):
    def document(self):
        root = ET.Element("TestRun")
        counters = {key: "0" for key in "failed error timeout aborted inconclusive passedButRunAborted notRunnable notExecuted disconnected warning completed inProgress pending".split()}
        counters.update(total="18", executed="18", passed="18")
        ET.SubElement(ET.SubElement(root, "ResultSummary", outcome="Completed"), "Counters", counters)
        definitions, entries, results = (ET.SubElement(root, key) for key in ("TestDefinitions", "TestEntries", "Results"))
        workspace = pathlib.Path(__file__).resolve().parents[1]
        manifest = json.loads((workspace / "docs/procurement-fixture-containment-cases.json").read_text())
        for case in manifest["cases"]:
            name, test_id = case["name"], case["id"]
            qualified = name.split("(", 1)[0]
            class_name, method = qualified.rsplit(".", 1)
            execution = str(uuid.uuid5(uuid.NAMESPACE_DNS, name))
            codebase = "/host/Legacy.Maliev.ProcurementService.Tests/bin/Release/net10.0/Legacy.Maliev.ProcurementService.Tests.dll"
            definition = ET.SubElement(definitions, "UnitTest", id=test_id, name=name, storage=codebase.lower())
            ET.SubElement(definition, "Execution", id=execution)
            ET.SubElement(definition, "TestMethod", className=class_name, name=method, codeBase=codebase, adapterTypeName="executor://xunit/VsTestRunner3/netcore/")
            ET.SubElement(entries, "TestEntry", testId=test_id, executionId=execution)
            ET.SubElement(results, "UnitTestResult", testId=test_id, executionId=execution, testName=name, outcome="Passed")
        return root

    def validate(self, document):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            ET.ElementTree(document).write(root / "synthetic.trx")
            guard.native_cases(root)

    def test_counter_and_summary_parent_relocation_or_nesting_fails(self):
        for mode in ("relocated-counters", "nested-counters", "nested-summary"):
            document = self.document(); summary = document.find("./ResultSummary"); counters = summary.find("./Counters")
            if mode == "relocated-counters": summary.remove(counters); document.append(counters)
            elif mode == "nested-counters": summary.remove(counters); ET.SubElement(summary, "Contradiction").append(counters)
            else: document.remove(summary); ET.SubElement(document, "Contradiction").append(summary)
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.validate(document)

    def test_duplicate_or_nested_method_execution_and_row_parents_fail(self):
        for mode in ("method", "execution", "nested-method", "nested-execution", "nested-entry", "nested-results"):
            document = self.document(); definition = document.find("./TestDefinitions/UnitTest")
            if mode in ("method", "nested-method"):
                parent = definition if mode == "method" else ET.SubElement(definition, "Contradiction")
                ET.SubElement(parent, "TestMethod", name="Foreign", className="Foreign", codeBase="/foreign.dll")
            elif mode in ("execution", "nested-execution"):
                parent = definition if mode == "execution" else ET.SubElement(definition, "Contradiction")
                ET.SubElement(parent, "Execution", id=str(uuid.uuid4()))
            elif mode == "nested-entry":
                parent = document.find("./TestEntries"); row = parent.find("./TestEntry"); parent.remove(row); ET.SubElement(parent, "Contradiction").append(row)
            else:
                parent = document.find("./Results"); document.remove(parent); ET.SubElement(document, "Contradiction").append(parent)
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.validate(document)

    def test_synthetic_authored_method_roster_and_joins_pass(self):
        self.validate(self.document())

    def test_missing_or_failed_execution_fails_despite_green_counters(self):
        for mode in ("missing", "failed"):
            document = self.document()
            row = document.find("./Results/UnitTestResult")
            if mode == "missing":
                document.find("./Results").remove(row)
            else:
                row.set("outcome", "Failed")
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.validate(document)

    def test_wrong_method_or_broken_join_fails(self):
        for mode in ("method", "join"):
            document = self.document()
            if mode == "method":
                document.find("./TestDefinitions/UnitTest/TestMethod").set("name", "Unreviewed")
            else:
                document.find("./TestEntries/TestEntry").set("executionId", str(uuid.uuid4()))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.validate(document)

    def test_duplicate_or_error_evidence_fails(self):
        for mode in ("duplicate", "error"):
            document = self.document()
            if mode == "error":
                ET.SubElement(document, "ErrorInfo")
            else:
                rows = document.findall("./Results/UnitTestResult")
                rows[1].set("executionId", rows[0].get("executionId"))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.validate(document)

    def test_summary_counter_runinfo_and_dll_custody_fail_closed(self):
        for mode in ("missing-outcome", "adverse-outcome", "duplicate-summary", "duplicate-counters", "runinfo", "missing-counter", "foreign-dll", "storage", "adapter"):
            document = self.document()
            if mode == "missing-outcome":
                del document.find("./ResultSummary").attrib["outcome"]
            elif mode == "adverse-outcome":
                document.find("./ResultSummary").set("outcome", "Failed")
            elif mode == "duplicate-summary":
                ET.SubElement(document, "ResultSummary", outcome="Failed")
            elif mode == "duplicate-counters":
                ET.SubElement(document, "Counters")
            elif mode == "runinfo":
                ET.SubElement(document, "RunInfo")
            elif mode == "missing-counter":
                del document.find("./ResultSummary/Counters").attrib["pending"]
            elif mode == "foreign-dll":
                document.find("./TestDefinitions/UnitTest/TestMethod").set("codeBase", "/foreign.dll")
            elif mode == "storage":
                document.find("./TestDefinitions/UnitTest").set("storage", "/foreign.dll")
            else:
                document.find("./TestDefinitions/UnitTest/TestMethod").set("adapterTypeName", "foreign")
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.validate(document)
        with self.assertRaises(ValueError):
            guard.provider(receipt(), "successful-lifecycle", "d" * 32)

    def test_timestamp_payload_and_expired_lease_fail(self):
        for field in ("Created", "StartedAt"):
            value = receipt(); value["Resources"][0][field] = "forbidden customer payload"
            with self.subTest(field=field), self.assertRaises(ValueError):
                guard.provider(value, "successful-lifecycle", "b" * 32)
        value = receipt(); value["Resources"][0]["Labels"]["maliev.codex.expires-utc"] = "2026-10-10T09:00:00+00:00"
        with self.assertRaises(ValueError):
            guard.provider(value, "successful-lifecycle", "b" * 32)


class OuterWitnessControls(unittest.TestCase):
    def files(self, root):
        ET.ElementTree(NativeRosterControls().document()).write(root / "synthetic.trx")
        directory = root / "fixture-containment"; directory.mkdir()
        normal = receipt()
        failed = receipt(); failed["Scenario"] = "partial-setup-failure"; failed["ResourceRunId"] = "d" * 32
        failed["ObservedOperationFailureTypes"] = ["System.IO.IOException"]
        for index, row in enumerate(failed["Resources"]):
            row["Id"] = str(index + 3) * 64; row["Volumes"] = [row["Id"]]
            row["Labels"]["maliev.codex.run"] = failed["ResourceRunId"]
        failed["ContainersAbsent"] = [row["Id"] for row in failed["Resources"]]
        failed["VolumesAbsent"] = list(failed["ContainersAbsent"])
        for value in (normal, failed):
            (directory / (value["Scenario"] + ".json")).write_text(json.dumps(value))
        expiry = {"Scenario": "forced-expiry", "ResourceRunId": "e" * 32, "ContainerId": "5" * 64,
                  "ParentRunId": "b" * 32, "Owner": "procurement-runtime-fixture", "Volumes": ["5" * 64],
                  "VolumesAbsent": ["5" * 64], "ExpiredBeforeCleanup": True, "ExitCode": 137,
                  "ElapsedSeconds": 3.0, "ContainerAbsent": True, "UnsettledOperations": 0,
                  "ObservedOperationFailureTypes": [], "PersistentData": False}
        (directory / "forced-expiry.json").write_text(json.dumps(expiry))
        process = {"pid": 17, "startTicks": 123, "group": 17, "session": 17, "executable": "/usr/share/dotnet/dotnet"}
        outer = {"schemaVersion": 3, "observationContract": "one-running-snapshot-full-id-census-v2", "runId": "b" * 32, "startedAtUtc": "2026-10-11T09:00:00+00:00",
                 "completedAtUtc": "2026-10-11T09:01:00+00:00", "testProcess": process, "launchProcess": dict(process, executable="/python3"), "expectedTestExecutable": process["executable"],
                 "testExitCode": 0, "observedProcesses": [dict(process, executable="/python3"), process], "ownedContainers": [str(i) * 64 for i in range(1, 6)],
                 "ownedVolumes": [str(i) * 64 for i in range(1, 6)], "sessions": ["c" * 32],
                 "remaining": [], "errorTypes": [], "commandFailures": [], "destructiveDockerActions": 0}
        outer["observedResources"] = []
        for value in (normal, failed):
            for row in value["Resources"]:
                outer["observedResources"].append({"id": row["Id"], "role": row["Role"], "creationKind": "testcontainers", "testcontainersSessionId": "c" * 32, "resourceRunId": value["ResourceRunId"], "parentRunId": "b" * 32,
                    "createdAt": "2026-10-11T09:00:00+00:00", "startedAt": "2026-10-11T09:00:01+00:00", "processId": 123,
                    "memoryBytes": row["MemoryBytes"], "memorySwapBytes": row["MemorySwapBytes"], "nanoCpus": row["NanoCpus"],
                    "expiresAt": "2026-10-11T09:32:00+00:00", "volumes": row["Volumes"], "hostIps": ["127.0.0.1"]})
        outer["observedResources"].append({"id": "5" * 64, "role": "forced-expiry-control", "creationKind": "docker-api-manual", "testcontainersSessionId": None, "resourceRunId": "e" * 32, "parentRunId": "b" * 32,
            "createdAt": "2026-10-11T09:00:00+00:00", "startedAt": "2026-10-11T09:00:01+00:00", "processId": 125,
            "memoryBytes": 67108864, "memorySwapBytes": 67108864, "nanoCpus": 100000000,
            "expiresAt": "2026-10-11T09:00:30+00:00", "volumes": ["5" * 64], "hostIps": []})
        (root / "outer-process-cleanup.json").write_text(json.dumps(outer))
        return outer, expiry

    def test_snapshot_contract_missing_fifth_resource_birth_or_late_resources_fail(self):
        for mode in ("missing-fifth", "wrong-birth", "wrong-parent", "late-session", "late-volume", "old-contract"):
            with tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory); outer, _ = self.files(root)
                if mode == "missing-fifth": outer["observedResources"].pop()
                elif mode == "wrong-birth": outer["observedResources"][0]["startedAt"] = "2026-10-10T09:00:00+00:00"
                elif mode == "wrong-parent": outer["observedResources"][0]["parentRunId"] = "a" * 32
                elif mode == "late-session": outer["remaining"] = ["session-container:" + "9" * 64]
                elif mode == "late-volume": outer["remaining"] = ["session-volume:late-volume"]
                else: outer["observationContract"] = "continuous-caps-unproven"
                (root / "outer-process-cleanup.json").write_text(json.dumps(outer))
                with self.subTest(mode=mode), self.assertRaises(ValueError): guard.verify(root)

    def test_role_specific_session_ownership_and_manual_correlation_are_strict(self):
        for mode in ("missing-pg", "invalid-pg", "foreign-pg", "foreign-all-snapshots", "manual-session", "manual-kind", "spoof-pg-kind", "wrong-manual-id", "wrong-expiry"):
            with tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory); outer, _ = self.files(root)
                pg, manual = outer["observedResources"][0], outer["observedResources"][-1]
                if mode == "missing-pg": pg["testcontainersSessionId"] = None
                elif mode == "invalid-pg": pg["testcontainersSessionId"] = "invalid"
                elif mode == "foreign-pg": pg["testcontainersSessionId"] = "d" * 32
                elif mode == "foreign-all-snapshots":
                    outer["sessions"] = ["d" * 32]
                    for row in outer["observedResources"][:-1]: row["testcontainersSessionId"] = "d" * 32
                elif mode == "manual-session": manual["testcontainersSessionId"] = "c" * 32
                elif mode == "manual-kind": manual["creationKind"] = "testcontainers"
                elif mode == "spoof-pg-kind": pg["creationKind"] = "docker-api-manual"
                elif mode == "wrong-manual-id": manual["id"] = "9" * 64
                else: manual["expiresAt"] = manual["startedAt"]
                (root / "outer-process-cleanup.json").write_text(json.dumps(outer))
                with self.subTest(mode=mode), self.assertRaises(ValueError): guard.verify(root)

    def test_command_failure_custody_never_qualifies_or_allows_raw_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory); outer, _ = self.files(root)
            failure = {"query": "inspect-container", "containerId": "a" * 64, "exitCode": 1, "category": "exact-container-not-found", "stderrBytes": 0, "stderrSha256": "a" * 64, "phase": "native-observation", "commandLaunchProcess": outer["launchProcess"], "durationMilliseconds": 1, "childTerminalObserved": True, "streamsClosed": True, "handleClosed": True}
            for raw in (False, True):
                outer["commandFailures"] = [dict(failure)]
                if raw: outer["commandFailures"][0]["rawStderr"] = "private-data"
                (root / "outer-process-cleanup.json").write_text(json.dumps(outer))
                with self.subTest(raw=raw), self.assertRaises(ValueError): guard.verify(root)

    def test_observer_launch_native_transition_passes_real_receipt_parser(self):
        import copy
        spec = importlib.util.spec_from_file_location("process_observer", pathlib.Path(__file__).with_name("observe-procurement-fixture-process.py"))
        observer = importlib.util.module_from_spec(spec); spec.loader.exec_module(observer)
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory); outer, _ = self.files(root)
            outer.update(observer.process_custody(outer["launchProcess"], outer["expectedTestExecutable"], outer["observedProcesses"]))
            (root / "outer-process-cleanup.json").write_text(json.dumps(outer))
            guard.verify(root)
            for field in ("pid", "startTicks", "group", "session", "executable"):
                mutated = copy.deepcopy(outer)
                mutated["testProcess"][field] = "/foreign" if field == "executable" else mutated["testProcess"][field] + 1
                mutated["observedProcesses"][-1] = mutated["testProcess"]
                (root / "outer-process-cleanup.json").write_text(json.dumps(mutated))
                with self.subTest(field=field), self.assertRaises(ValueError): guard.verify(root)

    def test_complete_synthetic_schema_passes_only_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory); self.files(root)
            self.assertFalse(guard.verify(root)["productionQualification"])

    def test_failed_outer_process_unknown_fields_remaining_or_missing_session_fail(self):
        for key, value in (("testExitCode", 1), ("ConnectionString", "forbidden"), ("remaining", ["process:17"]), ("sessions", []), ("errorTypes", ["TimeoutError"]), ("ownedContainers", ["1" * 64])):
            with tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory); outer, _ = self.files(root)
                outer[key] = value; (root / "outer-process-cleanup.json").write_text(json.dumps(outer))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    guard.verify(root)

    def test_expiry_before_cleanup_parent_volume_and_deadline_controls_fail(self):
        for key, value in (("ExpiredBeforeCleanup", False), ("ExitCode", 0), ("ElapsedSeconds", 20), ("ParentRunId", "a" * 32), ("VolumesAbsent", []), ("PersistentData", True)):
            with tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory); _, expiry = self.files(root)
                expiry[key] = value; (root / "fixture-containment/forced-expiry.json").write_text(json.dumps(expiry))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    guard.verify(root)



class FiniteReceiptControls(unittest.TestCase):
    def data(self):
        import copy
        cid="a"*64;run="b"*32;parent="c"*32;image="sha256:"+"d"*64
        labels={"maliev.codex.owner":"procurement-runtime-fixture","maliev.codex.run":run,"maliev.codex.parent-run":parent,"maliev.codex.role":"expiry-profile-bookworm","maliev.codex.persistent-data":"false","maliev.codex.expires-utc":"2026-10-12T00:00:30Z"}
        row={"ObservedAtUtc":"2026-10-12T00:00:00Z","ObservedTicks":1,"ContainerId":cid,"ImageId":image,"CreatedAt":"2026-10-12T00:00:00Z","StartedAt":"2026-10-12T00:00:01Z","FinishedAt":"2026-10-12T00:00:04Z","ProcessId":17,"Running":False,"OomKilled":False,"ExitCode":137,"MemoryBytes":67108864,"MemorySwapBytes":67108864,"NanoCpus":100000000,"Entrypoint":["sh","-c",'exec timeout --signal=INT --kill-after=1s 2 "$@"',"procurement-expiry-profile"],"Command":["sh","-c",'trap "" INT TERM; while :; do sleep 1; done'],"Labels":labels,"Mounts":[{"Type":"volume","Name":"original","Destination":"/data","ReadWrite":True}],"Bindings":[]}
        running=copy.deepcopy(row);running.update(Running=True,ObservedAtUtc="2026-10-12T00:00:02Z",ObservedTicks=2)
        stopped=copy.deepcopy(row);stopped.update(ObservedAtUtc="2026-10-12T00:00:04Z",ObservedTicks=3,ProcessId=0)
        value={"Scenario":"expiry-profile-bookworm","Profile":"bookworm","Image":"postgres:18.1-bookworm","ImageId":image,"ImageDigests":[],"Launcher":'exec timeout --signal=INT --kill-after=1s 2 "$@"' ,"ResourceRunId":run,"ContainerId":cid,"ParentRunId":parent,"Owner":"procurement-runtime-fixture","ScopeCaptured":True,"Volumes":["original"],"VolumesAbsent":["original"],"Acquired":row,"Running":running,"StoppedBeforeCleanup":stopped,"LauncherExpiryCandidate":False,"OwnerWatchdogInvoked":False,"StoppedByOwner":None,"OwnerActions":["remove-requested:"+cid],"FiniteLifecycleOwnerCleanupObserved":True,"FiniteLifecycleQualified":False,"ExternalTerminationExcluded":False,"NaturalExpiryProven":False,"ExitCode":137,"ElapsedSeconds":3,"ContainerAbsent":True,"PublicationSnapshotPendingCount":1,"PayloadWrittenBeforePublicationCompletion":True,"ObservedOperationFailureTypes":[],"PersistentData":False}
        observation={"id":cid,"resourceRunId":run,"startedAt":running["StartedAt"],"processId":17,"volumes":["original"],"acquisitionEligible":True,"finiteOwnerProfileScope":{"imageId":image,"entrypoint":row["Entrypoint"],"command":row["Command"],"mounts":[{"Name":"original","Destination":"/data","RW":True}],"labels":labels,"hostBindings":{"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"32769"}]}}}
        outer={"runId":parent,"testExitCode":0,"remaining":[],"errorTypes":[]}
        return value,observation,outer
    def test_synthetic_finite_schema_no_expiry_or_admission(self):
        result=guard.finite_receipt(*self.data());self.assertTrue(result["finiteOwnerLifecycleQualified"]);self.assertFalse(result["naturalExpiryProven"]);self.assertFalse(result["providerAdmission"])
    def test_refused_original_scope_is_ineligible(self):
        value,observation,outer=self.data();observation["acquisitionEligible"]=False
        with self.assertRaises(ValueError):guard.finite_receipt(value,observation,outer)
    def test_final_birth_lease_and_mount_drift_fail(self):
        for key,replacement in [("StartedAt","2026-10-12T00:00:02Z"),("CreatedAt","2026-10-12T00:00:01Z")]:
            value,observation,outer=self.data();value["StoppedBeforeCleanup"][key]=replacement
            with self.assertRaises(ValueError):guard.finite_receipt(value,observation,outer)
        value,observation,outer=self.data();value["StoppedBeforeCleanup"]["Labels"]["maliev.codex.expires-utc"]="2026-10-12T00:00:31Z"
        with self.assertRaises(ValueError):guard.finite_receipt(value,observation,outer)
    def test_blocked_publication_or_absent_terminal_settlement_fails(self):
        for key,replacement in [("PublicationSnapshotPendingCount",2),("ObservedOperationFailureTypes",["IOException"]),("ContainerAbsent",False)]:
            value,observation,outer=self.data();value[key]=replacement
            with self.assertRaises(ValueError):guard.finite_receipt(value,observation,outer)
        value,observation,outer=self.data();outer["remaining"]=["process:17"]
        with self.assertRaises(ValueError):guard.finite_receipt(value,observation,outer)
    def test_stopped_observation_before_finish_fails(self):
        value,observation,outer=self.data();value["StoppedBeforeCleanup"]["ObservedAtUtc"]="2026-10-12T00:00:03Z"
        with self.assertRaises(ValueError):guard.finite_receipt(value,observation,outer)


class ActualRecoveryTaskSourceControls(unittest.TestCase):
    def test_actual_task_is_registered_before_cancellable_wrapper(self):
        source=(pathlib.Path(__file__).resolve().parents[1]/"Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementImageExpiryProfileWitnessTests.cs").read_text()
        self.assertLess(source.index("var recoveryRead = Task.Run"),source.index("lifetime.TrackOwnedTask(recoveryRead)"))
        self.assertLess(source.index("lifetime.TrackOwnedTask(recoveryRead)"),source.index("await recoveryRead.WaitAsync(cleanupDeadline.Token)"))
    def test_total_lease_cleanup_reserve_and_error_custody_are_authored(self):
        source=(pathlib.Path(__file__).resolve().parents[1]/"Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementImageExpiryProfileWitnessTests.cs").read_text()
        self.assertNotIn("realLease.Token",source)
        self.assertEqual(2,source.count("new CancellationTokenSource(TimeSpan.FromSeconds(15))"))
        self.assertEqual(2,source.count("new CancellationTokenSource(realBudget.RemainingCleanupTime())"))
        self.assertEqual(2,source.count("RethrowSeamFailures(primaryFailure, cleanupFailure)"))
        self.assertIn("RecoveryRead_ExpiredTotalLeaseRefusesFalseSettlement",source)
        self.assertIn("TimeSpan.FromSeconds(20) - clock.GetElapsedTime(started)",source)
        self.assertIn("Assert.Same(primary, aggregate.InnerExceptions[0])",source)
        self.assertIn("Assert.Same(cleanup, aggregate.InnerExceptions[1])",source)
    def test_runtime_seams_and_existing_lifetime_ledger_hook_are_authored(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        source=(root/"Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementImageExpiryProfileWitnessTests.cs").read_text()
        lifetime=(root/"Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs").read_text()
        self.assertIn("internal void TrackOwnedTask(Task operation) => Observe(operation);",lifetime)
        self.assertIn("RecoveryRead_BlockedTaskRemainsOwnedAfterDeadline",source)
        self.assertIn("RecoveryRead_PostTimeoutFaultRetainsOriginalReference",source)
        self.assertIn("Assert.Same(expected, actual)",source)
        self.assertIn("Assert.Contains(actualRead, lifetime.UnsettledOperations)",source)

if __name__ == "__main__":
    unittest.main()


class ProvisionalDiscoveryControls(unittest.TestCase):
    def test_null_source_admission_cannot_start_native_discovery(self):
        extension = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs/procurement-fixture-containment-cases.json").read_text())["finiteOwnerExtension"]
        import os
        root=pathlib.Path(__file__).resolve().parents[1]
        binding=json.loads((root/'docs/procurement-finite-owner-source-binding.json').read_text())
        binding['bootstrapReviewedProducer']=None;binding['bootstrapSourceAdmission']=None
        with tempfile.TemporaryDirectory() as directory:
            isolated=pathlib.Path(directory);(isolated/'docs').mkdir();(isolated/'scripts').mkdir()
            (isolated/'docs/procurement-finite-owner-source-binding.json').write_text(json.dumps(binding))
            from unittest.mock import patch
            with patch.object(guard,'__file__',str(isolated/'scripts/verify-procurement-fixture-containment.py')),patch.dict(os.environ,{'MALIEV_FINITE_OWNER_DISCOVERY':'reviewed-source-only'},clear=False),patch.object(guard.subprocess,'run') as run,patch.object(guard.subprocess,'check_output') as output:
                with self.assertRaisesRegex(ValueError,'Real source producer'):guard.finite_bootstrap(extension)
                run.assert_not_called();output.assert_not_called()

    def test_unreviewed_discovery_keeps_original_eighteen_guid_pins(self):
        from unittest.mock import patch
        extension = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs/procurement-fixture-containment-cases.json").read_text())["finiteOwnerExtension"]
        document = NativeRosterControls().document()
        document.set("id", str(uuid.uuid4()))
        for case in extension["cases"]:
            name = case["name"]; test_id = str(uuid.uuid4()); execution = str(uuid.uuid4())
            qualified = name.split("(", 1)[0]; cls, method = qualified.rsplit(".", 1)
            codebase = "/host/Legacy.Maliev.ProcurementService.Tests/bin/Release/net10.0/Legacy.Maliev.ProcurementService.Tests.dll"
            definition = ET.SubElement(document.find("TestDefinitions"), "UnitTest", id=test_id, name=name, storage=codebase.lower())
            ET.SubElement(definition, "Execution", id=execution)
            ET.SubElement(definition, "TestMethod", className=cls, name=method, codeBase=codebase, adapterTypeName="executor://xunit/VsTestRunner3/netcore/")
            ET.SubElement(document.find("TestEntries"), "TestEntry", testId=test_id, executionId=execution)
            ET.SubElement(document.find("Results"), "UnitTestResult", testId=test_id, executionId=execution, testName=name, outcome="Passed")
        counters = document.find("./ResultSummary/Counters")
        for key in ("total", "executed", "passed"): counters.set(key, "23")
        with tempfile.TemporaryDirectory() as directory, patch.object(guard, "finite_bootstrap", return_value=extension["cases"]):
            root = pathlib.Path(directory); path = root / "synthetic.trx"
            ET.ElementTree(document).write(path)
            self.assertEqual(5, len(guard.native_cases(root, True)))
            for mode in ("old-guid-drift", "skipped", "failed", "missing-definition", "new-name-permutation"):
                changed = ET.fromstring(ET.tostring(document))
                if mode == "new-name-permutation":
                    definitions = list(changed.find("TestDefinitions"))[-2:]
                    rows = list(changed.find("Results"))[-2:]
                    first, second = rows[0].get("testName"), rows[1].get("testName")
                    rows[0].set("testName", second); definitions[0].set("name", second)
                    rows[1].set("testName", first); definitions[1].set("name", first)
                elif mode == "old-guid-drift": changed.find("./Results/UnitTestResult").set("testId", str(uuid.uuid4()))
                elif mode == "missing-definition": changed.find("TestDefinitions").remove(changed.find("./TestDefinitions/UnitTest"))
                else: changed.find("./Results/UnitTestResult").set("outcome", "NotExecuted" if mode == "skipped" else "Failed")
                ET.ElementTree(changed).write(path)
                with self.subTest(mode=mode), self.assertRaises(ValueError): guard.native_cases(root, True)

    def test_discovery_rejects_missing_receipts_unsettled_workers_or_uncertain_absence(self):
        from unittest.mock import patch
        for mode in ("missing-receipt", "unsettled-operation", "remaining-worker", "uncertain-absence"):
            with tempfile.TemporaryDirectory() as directory, patch.object(guard, "native_cases", return_value=[]):
                root = pathlib.Path(directory); outer, _ = OuterWitnessControls().files(root)
                receipt_path = root / "fixture-containment/successful-lifecycle.json"
                if mode == "missing-receipt": receipt_path.unlink()
                elif mode == "unsettled-operation":
                    value = json.loads(receipt_path.read_text()); value["UnsettledOperations"] = 1
                    receipt_path.write_text(json.dumps(value))
                elif mode == "remaining-worker": outer["remaining"] = ["owned-worker-still-running"]
                else: outer["errorTypes"] = ["TimeoutError"]
                (root / "outer-process-cleanup.json").write_text(json.dumps(outer))
                with self.subTest(mode=mode), self.assertRaises((ValueError, FileNotFoundError)):
                    guard.verify(root, True)

    def test_positive_image_theory_is_enabled_and_admission_precedes_docker_client(self):
        text = (pathlib.Path(__file__).resolve().parents[1] / "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementImageExpiryProfileWitnessTests.cs").read_text(encoding="utf-8")
        attributes = text.split("public async Task ImageSpecificControl_HasFiniteOwnerCleanup", 1)[0].rsplit("    [Theory]", 1)
        self.assertEqual(2, len(attributes))
        self.assertNotIn("Skip", attributes[1])
        self.assertIn('[InlineData("18.1-bookworm", "bookworm")]', attributes[1])
        self.assertIn('[InlineData("18.1-alpine", "alpine")]', attributes[1])
        self.assertIn('producer.ValueKind != JsonValueKind.String', text)
        self.assertIn('(!bootstrap && binding.GetProperty("releaseAllowed").ValueKind != JsonValueKind.True)', text)
        self.assertIn('throw new InvalidOperationException("Witness source admission is unbound.");', text)
        body = text.split("public async Task ImageSpecificControl_HasFiniteOwnerCleanup", 1)[1]
        self.assertLess(body.index("RequireImageAdmission();"), body.index("new DockerClientConfiguration"))


class SharedSourceAdmissionWiringControls(unittest.TestCase):
    def test_both_existing_build_paths_use_same_preallocation_source_guard(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        for filename in ("_build-and-test.yml", "procurement-fixture-containment.yml"):
            text = (root / ".github/workflows" / filename).read_text(encoding="utf-8")
            self.assertIn("MALIEV_FINITE_OWNER_SOURCE_HEAD:", text)
            mode = "qualified-full-only" if filename == "_build-and-test.yml" else "reviewed-source-only"
            self.assertIn("MALIEV_FINITE_OWNER_DISCOVERY: '" + mode + "'", text)
            self.assertLess(text.index("verify-procurement-fixture-containment.py --source-admission"), text.index("dotnet restore"))
        source = (root / "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementImageExpiryProfileWitnessTests.cs").read_text(encoding="utf-8")
        self.assertIn("pins.Length != 9", source)
        self.assertIn("[Theory]", source)
        self.assertNotIn("[Theory(Skip = ", source)

from unittest.mock import patch


class SourceAdmissionBehaviorControls(unittest.TestCase):
    def test_focused_uses_existing_bootstrap_guard_only(self):
        with patch.object(guard,'finite_bootstrap') as bootstrap, patch.object(guard,'finite_activation') as full:
            guard.source_admission({'enabled':False},'reviewed-source-only')
            bootstrap.assert_called_once_with({'enabled':False});full.assert_not_called()

    def test_full_rejects_incomplete_identity_custody_without_bootstrap(self):
        for ids in [[],[1,2,3,4]]:
            with patch.object(guard,'finite_activation',return_value=ids), patch.object(guard,'finite_bootstrap') as bootstrap:
                with self.assertRaisesRegex(ValueError,'reviewed exact23'):guard.source_admission({'enabled':False},'qualified-full-only')
                bootstrap.assert_not_called()

    def test_unknown_lane_never_enters_either_admission_guard(self):
        with patch.object(guard,'finite_bootstrap') as bootstrap, patch.object(guard,'finite_activation') as full:
            with self.assertRaisesRegex(ValueError,'Unknown'):guard.source_admission({},'foreign')
            bootstrap.assert_not_called();full.assert_not_called()



class PositivePostimageAdmissionControls(unittest.TestCase):
    def test_isolated_null_fixture_refuses_focused_and_full_without_git_or_native(self):
        import os
        root=pathlib.Path(__file__).resolve().parents[1]
        binding=json.loads((root/'docs/procurement-finite-owner-source-binding.json').read_text())
        extension=json.loads((root/'docs/procurement-fixture-containment-cases.json').read_text())['finiteOwnerExtension']
        # This negative is independent of the repository's current bootstrap admission.
        binding['bootstrapReviewedProducer']=None
        binding['bootstrapSourceAdmission']=None
        with tempfile.TemporaryDirectory() as directory:
            isolated=pathlib.Path(directory);(isolated/'docs').mkdir();(isolated/'scripts').mkdir()
            (isolated/'docs/procurement-finite-owner-source-binding.json').write_text(json.dumps(binding))
            with patch.object(guard,'__file__',str(isolated/'scripts/verify-procurement-fixture-containment.py')), patch.dict(os.environ,{'MALIEV_FINITE_OWNER_DISCOVERY':'reviewed-source-only'},clear=False), patch.object(guard.subprocess,'run') as run, patch.object(guard.subprocess,'check_output') as output:
                with self.assertRaisesRegex(ValueError,'Real source producer'):guard.source_admission(extension,'reviewed-source-only')
                with self.assertRaisesRegex(ValueError,'reviewed exact23'):guard.source_admission(extension,'qualified-full-only')
                run.assert_not_called();output.assert_not_called()

    def test_actual_binding_requires_real_producer_custody_and_keeps_full_inactive(self):
        import os
        root=pathlib.Path(__file__).resolve().parents[1]
        binding=json.loads((root/'docs/procurement-finite-owner-source-binding.json').read_text())
        extension=json.loads((root/'docs/procurement-fixture-containment-cases.json').read_text())['finiteOwnerExtension']
        self.assertIsNone(binding['reviewedProducer']);self.assertIsNone(binding['nativeIds'])
        self.assertIs(binding['releaseAllowed'],False);self.assertIs(extension['enabled'],False)
        self.assertTrue(all(case['id'] is None for case in extension['cases']))
        with self.assertRaisesRegex(ValueError,'reviewed exact23'):guard.source_admission(extension,'qualified-full-only')
        # The actual admitted document must pass the real guard: SHA/blob + producer Git
        # bytes/ancestry + original declared source + focused-only restrictions.
        if binding['bootstrapSourceAdmission'] is True:
            self.assertEqual('reviewed-source-only',os.environ.get('MALIEV_FINITE_OWNER_DISCOVERY'))
            guard.source_admission(extension,'reviewed-source-only')
        else:
            self.assertIsNone(binding['bootstrapSourceAdmission']);self.assertIsNone(binding['bootstrapReviewedProducer'])
            with patch.dict(os.environ,{'MALIEV_FINITE_OWNER_DISCOVERY':'reviewed-source-only'},clear=False):
                with self.assertRaisesRegex(ValueError,'Real source producer'):guard.source_admission(extension,'reviewed-source-only')
