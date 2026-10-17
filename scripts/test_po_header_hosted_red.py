"""Synthetic TRX guard tests only; never start SDK, PostgreSQL or a source host."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import uuid
import xml.etree.ElementTree as ET

MODULE_PATH = Path(__file__).with_name("verify-po-header-hosted-red.py")
SPEC = importlib.util.spec_from_file_location("po_header_red", MODULE_PATH)
RED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RED)
CONTRACT = json.loads((MODULE_PATH.parent.parent / "docs/procurement-po-header-hosted-red-contract.json").read_text(encoding="utf-8"))


class HostedRedTrxTests(unittest.TestCase):
    def fixture(self):
        doc = ET.Element("TestRun")
        summary = ET.SubElement(doc, "ResultSummary", outcome="Failed")
        ET.SubElement(summary, "Counters", **{key: str(value) for key, value in CONTRACT["expectedCounters"].items()})
        defs, entries, results = (ET.SubElement(doc, name) for name in ("TestDefinitions", "TestEntries", "Results"))
        notices = ET.SubElement(summary, "RunInfos")
        for index, case in enumerate(CONTRACT["cases"], 1):
            test_id, execution = str(uuid.UUID(int=index)), str(uuid.UUID(int=index + 100))
            definition = ET.SubElement(defs, "UnitTest", id=test_id, name=case["name"])
            ET.SubElement(definition, "Execution", id=execution)
            ET.SubElement(definition, "TestMethod", className=CONTRACT["className"], name=CONTRACT["methodName"])
            ET.SubElement(entries, "TestEntry", testId=test_id, executionId=execution)
            result = ET.SubElement(results, "UnitTestResult", testId=test_id, executionId=execution,
                                   testName=case["name"], outcome=case["outcome"])
            if case["outcome"] == "Failed":
                info = ET.SubElement(notices, "RunInfo", outcome="Error", computerName="synthetic", timestamp="2026-10-17T00:00:00Z")
                ET.SubElement(info, "Text").text = "[xUnit.net 00:00:01.23]     " + case["name"] + " [FAIL]"
                error = ET.SubElement(ET.SubElement(result, "Output"), "ErrorInfo")
                category, expected = CONTRACT["failureCategory"], case["bindingFailure"]
                ET.SubElement(error, "Message").text = (
                    category["outerType"] + " : The JSON value could not be converted to " + category["outerTarget"]
                    + ". Path: " + category["propertyPath"] + " | LineNumber: 0 | BytePositionInLine: " + str(expected["bytePosition"]) + ".\n"
                    + "---- " + category["innerType"] + " : Cannot get the value of a token type '" + expected["tokenType"] + "' as a string.")
                bind, test = category["requiredFrames"]
                get_string = category["diagnosticInternalFrames"][0]
                ET.SubElement(error, "StackTrace").text = (
                    "   at " + bind + "(String payload) in /repo/HeaderTests.cs:line 309\n"
                    "   at " + test + "(String token, String expected) in /repo/HeaderTests.cs:line 84\n"
                    "   at " + get_string + "()")
        return doc

    def verify(self, doc, extra=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            qualified = copy.deepcopy(doc)
            for node in qualified.iter():
                if not node.tag.startswith("{"):
                    node.tag = "{" + RED.TRX_NAMESPACE + "}" + node.tag
            ET.ElementTree(qualified).write(root / "baseline.trx", encoding="utf-8")
            if extra:
                ET.ElementTree(qualified).write(root / "extra.trx", encoding="utf-8")
            return RED.verify_trx(root, CONTRACT)

    def raw(self):
        qualified = self.fixture()
        for node in qualified.iter():
            node.tag = "{" + RED.TRX_NAMESPACE + "}" + node.tag
        return ET.tostring(qualified, encoding="utf-8")

    def verify_raw(self, data):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "baseline.trx").write_bytes(data)
            return RED.verify_trx(root, CONTRACT)

    def test_exact_source_derived_roster_accepts(self):
        proof = self.verify(self.fixture())
        self.assertEqual((9, 4, 5), (proof["executed"], proof["passed"], proof["failed"]))

    def test_general_nonzero_or_wrong_failure_category_is_not_red(self):
        for message in ("NpgsqlException : fixture failed", "Xunit.Sdk.EqualException : mismatch",
                        "Newtonsoft.Json.JsonReaderException : wrong token",
                        "System.Text.Json.JsonException : wrong target Int32"):
            with self.subTest(message=message):
                doc = self.fixture()
                doc.find(".//ErrorInfo/Message").text = message
                with self.assertRaises(ValueError):
                    self.verify(doc)

    def test_missing_duplicate_or_unexpected_identity_is_rejected(self):
        for mutation in ("missing", "duplicate", "unexpected"):
            with self.subTest(mutation=mutation):
                doc = self.fixture()
                results = doc.find("Results")
                if mutation == "missing":
                    results.remove(results[0])
                elif mutation == "duplicate":
                    results[0].set("testName", results[1].get("testName"))
                else:
                    results[0].set("testName", "Some.Other.Test")
                with self.assertRaises(ValueError):
                    self.verify(doc)

    def test_execution_joins_and_method_are_required(self):
        for path, attribute, replacement in (("TestEntries/TestEntry", "executionId", str(uuid.UUID(int=999))),
                                              ("TestDefinitions/UnitTest/TestMethod", "name", "OtherMethod")):
            with self.subTest(path=path):
                doc = self.fixture()
                doc.find(path).set(attribute, replacement)
                with self.assertRaises(ValueError):
                    self.verify(doc)

    def test_counts_outcomes_and_failure_site_are_required(self):
        for mutation in ("count", "outcome", "stack"):
            with self.subTest(mutation=mutation):
                doc = self.fixture()
                if mutation == "count":
                    doc.find("ResultSummary/Counters").set("failed", "9")
                elif mutation == "outcome":
                    doc.find("Results/UnitTestResult").set("outcome", "Failed")
                else:
                    doc.find(".//ErrorInfo/StackTrace").text = "InitializeAsync"
                with self.assertRaises(ValueError):
                    self.verify(doc)

    def test_multiple_trx_and_runner_error_are_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(self.fixture(), extra=True)
        doc = self.fixture()
        run_infos = ET.SubElement(doc.find("ResultSummary"), "RunInfos")
        ET.SubElement(run_infos, "RunInfo", outcome="Error")
        with self.assertRaises(ValueError):
            self.verify(doc)

    def test_outer_exception_type_requires_exact_anchored_delimiter(self):
        for prefix in ("System.Text.Json.JsonExceptionSpoof", "FakeSystem.Text.Json.JsonException",
                       "System.Text.Json.JsonException.Other", "prefix System.Text.Json.JsonException"):
            with self.subTest(prefix=prefix):
                doc = self.fixture()
                message = doc.find(".//ErrorInfo/Message")
                message.text = message.text.replace(CONTRACT["failureCategory"]["outerType"], prefix, 1)
                with self.assertRaises(ValueError):
                    self.verify(doc)

    def test_required_methods_must_be_real_exact_frames(self):
        first, second = CONTRACT["failureCategory"]["requiredFrames"]
        get_string = CONTRACT["failureCategory"]["diagnosticInternalFrames"][0]
        for bad in (first + "(System.String value)", "text at " + first + "(System.String value)",
                    "   at " + first + "Spoof(System.String value)", "   at " + first + ".Other()",
                    "   at " + first + "(System.String value) arbitrary suffix"):
            with self.subTest(frame=bad):
                doc = self.fixture()
                doc.find(".//ErrorInfo/StackTrace").text = bad + "\n   at " + second + "(System.String token, System.String expected)\n   at " + get_string + "()"
                with self.assertRaises(ValueError):
                    self.verify(doc)

    def test_real_frames_without_source_suffix_are_accepted(self):
        doc = self.fixture()
        for stack in doc.findall(".//ErrorInfo/StackTrace"):
            stack.text = "\n".join("   at " + frame + ("()" if frame.endswith(".GetString") else "(System.String value)")
                                   for frame in CONTRACT["failureCategory"]["requiredFrames"])
        self.verify(doc)

    def test_actual_wrapper_rejects_wrong_dto_property_token_or_inner_chain(self):
        for mutation in ("dto", "property", "token", "position", "line", "inner-type", "missing-inner", "extra-line"):
            with self.subTest(mutation=mutation):
                doc = self.fixture()
                node = doc.find(".//ErrorInfo/Message")
                if mutation == "dto":
                    node.text = node.text.replace(CONTRACT["failureCategory"]["outerTarget"], "System.String")
                elif mutation == "property":
                    node.text = node.text.replace("$.SupplierContactPerson", "$.Notes")
                elif mutation == "token":
                    node.text = node.text.replace("'Number'", "'True'")
                elif mutation == "position":
                    node.text = node.text.replace("BytePositionInLine: 28.", "BytePositionInLine: 29.")
                elif mutation == "line":
                    node.text = node.text.replace("LineNumber: 0", "LineNumber: 1")
                elif mutation == "inner-type":
                    node.text = node.text.replace("System.InvalidOperationException", "System.InvalidOperationExceptionSpoof")
                elif mutation == "missing-inner":
                    node.text = node.text.splitlines()[0]
                else:
                    node.text += "\nextra exception"
                with self.assertRaises(ValueError):
                    self.verify(doc)

    def test_recorded_internal_stack_layouts_are_diagnostic_only(self):
        bind, test = CONTRACT["failureCategory"]["requiredFrames"]
        for internal in ("System.Text.Json.Utf8JsonReader.GetString()",
                         "System.Text.Json.ThrowHelper.ThrowInvalidOperationException_ExpectedString(JsonTokenType tokenType)", None):
            with self.subTest(internal=internal):
                doc = self.fixture()
                for node in doc.findall(".//ErrorInfo/StackTrace"):
                    node.text = ("   at " + bind + "(String payload) in /repo/HeaderTests.cs:line 284\n"
                                 "   at " + test + "(String token, String expected) in /repo/HeaderTests.cs:line 80")
                    if internal is not None:
                        node.text += "\n   at " + internal
                self.verify(doc)

    def test_both_core_binding_sites_are_mandatory_with_real_boundaries(self):
        for site in CONTRACT["failureCategory"]["requiredFrames"]:
            for mutation in ("missing", "suffix", "nonframe"):
                with self.subTest(site=site, mutation=mutation):
                    doc = self.fixture()
                    node = doc.find(".//ErrorInfo/StackTrace")
                    frame = next(line for line in node.text.splitlines() if line.lstrip().startswith("at " + site + "("))
                    replacement = "" if mutation == "missing" else frame.replace(site, site + "Spoof") if mutation == "suffix" else frame.lstrip().removeprefix("at ")
                    node.text = node.text.replace(frame, replacement)
                    with self.assertRaises(ValueError):
                        self.verify(doc)

    def test_utf8_and_utf8_bom_are_accepted(self):
        for prefix in (b"", b"\xef\xbb\xbf"):
            with self.subTest(prefix=prefix):
                self.verify_raw(prefix + self.raw())

    def test_non_utf8_and_declarations_are_rejected_before_parse(self):
        xml = self.raw()
        samples = [b"\xff" + xml, xml.decode("utf-8").encode("utf-16"), xml.decode("utf-8").encode("utf-16-le"),
                   b'<!DOCTYPE TestRun [<!ENTITY x "text">]>' + xml,
                   b'\xef\xbb\xbf<!DOCTYPE TestRun [<!ENTITY x "text">]>' + xml,
                   b'<!ENTITY x "text">' + xml]
        for data in samples:
            with self.subTest(prefix=data[:30]), mock.patch.object(RED.ET, "fromstring", side_effect=AssertionError("Parser must not run")):
                with self.assertRaises((ValueError, UnicodeError)):
                    self.verify_raw(data)

    def test_xml_read_is_bounded_at_max_plus_one(self):
        reader = mock.MagicMock()
        reader.read.return_value = b"x" * (RED.MAX_TRX_BYTES + 1)
        reader.__enter__.return_value = reader
        path = mock.Mock()
        path.open.return_value = reader
        with mock.patch.object(RED.ET, "fromstring", side_effect=AssertionError("Parser must not run")):
            with self.assertRaises(ValueError):
                RED.read_trx(path)
        reader.read.assert_called_once_with(RED.MAX_TRX_BYTES + 1)

    def test_exact_size_limit_is_accepted(self):
        raw = self.raw()
        self.verify_raw(raw + b" " * (RED.MAX_TRX_BYTES - len(raw)))

    def test_namespace_root_and_direct_structure_are_required(self):
        for mutation in ("foreign", "wrapper", "nested-results", "duplicate-summary", "foreign-child"):
            with self.subTest(mutation=mutation):
                doc = self.fixture()
                if mutation == "foreign":
                    doc.tag = "{urn:foreign}TestRun"
                elif mutation == "wrapper":
                    wrapper = ET.Element("Wrapper")
                    wrapper.append(doc)
                    doc = wrapper
                elif mutation == "nested-results":
                    results = doc.find("Results")
                    doc.remove(results)
                    ET.SubElement(doc, "Wrapper").append(results)
                elif mutation == "duplicate-summary":
                    doc.append(copy.deepcopy(doc.find("ResultSummary")))
                else:
                    doc.find("Results/UnitTestResult").tag = "{urn:foreign}UnitTestResult"
                with self.assertRaises(ValueError):
                    self.verify(doc)

    def test_hidden_namespaced_duplicate_structures_are_rejected(self):
        for element in ("ResultSummary", "Counters", "RunInfo", "UnitTest", "TestEntry", "UnitTestResult"):
            with self.subTest(element=element):
                doc = self.fixture()
                duplicate = copy.deepcopy(doc.find(".//" + element))
                if element == "ResultSummary":
                    duplicate.set("outcome", "Passed")
                elif element == "Counters":
                    duplicate.set("failed", "0")
                ET.SubElement(doc, "Wrapper").append(duplicate)
                with self.assertRaises(ValueError):
                    self.verify(doc)

    def test_failure_notices_must_biject_with_validated_failed_rows(self):
        for mutation in ("missing", "duplicate", "unexpected", "wrong-category", "four-spaces",
                         "assembly-prefix", "trailing-space", "extra-text", "exception-child"):
            with self.subTest(mutation=mutation):
                doc = self.fixture()
                notices = doc.find("ResultSummary/RunInfos")
                first = notices[0]
                if mutation == "missing":
                    notices.remove(first)
                elif mutation == "duplicate":
                    notices[-1].find("Text").text = first.findtext("Text")
                elif mutation == "unexpected":
                    first.find("Text").text = "[xUnit.net 00:00:01.23]     Other.Test [FAIL]"
                elif mutation == "wrong-category":
                    first.set("outcome", "Warning")
                elif mutation == "four-spaces":
                    first.find("Text").text = first.findtext("Text").replace("]     ", "]    ")
                elif mutation == "assembly-prefix":
                    first.find("Text").text = first.findtext("Text").replace("]     ", "] assembly:     ")
                elif mutation == "trailing-space":
                    first.find("Text").text += " "
                elif mutation == "extra-text":
                    ET.SubElement(first, "Text").text = "duplicate"
                else:
                    ET.SubElement(first, "Exception").text = "unexpected"
                with self.assertRaises(ValueError):
                    self.verify(doc)


class OwnedCommandCleanupTests(unittest.TestCase):
    def test_build_disables_shared_compilation(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            (evidence / "synthetic-build.log").write_text("0 Warning(s)\n0 Error(s)\n", encoding="utf-8")
            with mock.patch.object(RED, "command", return_value=0) as command:
                RED.build(evidence, evidence, "synthetic-build")
            self.assertIn("-p:UseSharedCompilation=false", command.call_args.args[1])

    def custody(self):
        return {"bootId": "synthetic-boot", "ownerUid": 1000, "ownerRunId": "run", "ownerJob": "job",
                "leaderPid": 1234, "group": 1234, "session": 1234, "leaderStartTicks": 200,
                "started": True, "verifiedAbsent": False}

    def member(self):
        return {"pid": 1234, "group": 1234, "session": 1234, "startTicks": 200, "uid": 1000, "state": "S"}

    def invoke(self, timeout=False, cleanup_failure=False):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            process = mock.Mock(pid=1234, returncode=0)
            process.wait.side_effect = ([RED.subprocess.TimeoutExpired(["dotnet"], 2), 0]
                                        if timeout else [0, 0])
            cleanup = ValueError("synthetic cleanup failure") if cleanup_failure else None
            with mock.patch.object(RED, "settle_command_groups"), \
                    mock.patch.object(RED, "boot_id", return_value="synthetic-boot"), \
                    mock.patch.object(RED.os, "getuid", return_value=1000), \
                    mock.patch.object(RED, "actual_start_utc", return_value="2026-10-17T00:00:00+00:00"), \
                    mock.patch.object(RED, "process_identity", return_value=self.member()), \
                    mock.patch.object(RED, "cleanup_group", side_effect=cleanup) as closer, \
                    mock.patch.object(RED, "group_members", return_value=[]), \
                    mock.patch.object(RED.subprocess, "Popen", return_value=process) as popen:
                try:
                    return RED.command(evidence, ["dotnet", "test"], evidence, "synthetic", 2)
                finally:
                    popen.assert_called_once()
                    self.assertIs(True, popen.call_args.kwargs["start_new_session"])
                    self.assertNotIn("VSTestCollect", popen.call_args.kwargs["env"])
                    closer.assert_called_once()

    def test_success_closes_owned_group_before_return(self):
        self.assertEqual(0, self.invoke())

    def test_timeout_preserves_primary_after_verified_cleanup(self):
        with self.assertRaises(RED.subprocess.TimeoutExpired):
            self.invoke(timeout=True)

    def test_timeout_and_cleanup_failures_are_both_retained(self):
        with self.assertRaises(BaseExceptionGroup) as raised:
            self.invoke(timeout=True, cleanup_failure=True)
        self.assertIsInstance(raised.exception.exceptions[0], RED.subprocess.TimeoutExpired)
        self.assertIsInstance(raised.exception.exceptions[1], ValueError)

    def test_graceful_then_exact_group_kill_and_absence(self):
        member = self.member()
        with mock.patch.object(RED, "group_members", side_effect=[[member], [member], [member], [member], []]), \
                mock.patch.object(RED.time, "monotonic", side_effect=[0, 11, 20]), \
                mock.patch.object(RED.time, "sleep") as sleeper, \
                mock.patch.object(RED.os, "killpg") as signal_group:
            RED.cleanup_group(self.custody())
        self.assertEqual([mock.call(1234, RED.signal.SIGTERM), mock.call(1234, RED.signal.SIGKILL)],
                         signal_group.call_args_list)
        sleeper.assert_not_called()

    def test_changed_custody_never_signals_and_blocks_cleanup(self):
        for mutation in ("uid", "startTicks", "session", "other-group"):
            with self.subTest(mutation=mutation):
                member = self.member()
                member[{"other-group": "group"}.get(mutation, mutation)] += 1
                fake_path = mock.Mock()
                fake_path.name = "1234"
                proc_root = mock.Mock()
                proc_root.iterdir.return_value = [fake_path]
                with mock.patch.dict(RED.os.environ, GITHUB_RUN_ID="run", GITHUB_JOB="job"), \
                        mock.patch.object(RED.os, "getuid", return_value=1000), \
                        mock.patch.object(RED, "boot_id", return_value="synthetic-boot"), \
                        mock.patch.object(RED, "Path", return_value=proc_root), \
                        mock.patch.object(RED, "process_identity", return_value=member), \
                        mock.patch.object(RED.os, "killpg") as signal_group:
                    with self.assertRaises(ValueError):
                        RED.cleanup_group(self.custody())
                    signal_group.assert_not_called()

    def test_unsettled_workers_block_source_restoration(self):
        with mock.patch.object(RED, "settle_command_groups", side_effect=ValueError("group remains")), \
                mock.patch.object(RED, "git") as git:
            with self.assertRaises(ValueError):
                RED.restore(Path("."), CONTRACT, {}, Path("."), "synthetic-head")
            git.assert_not_called()


class CandidateSourceCustodyTests(unittest.TestCase):
    def sources(self):
        root = MODULE_PATH.parent.parent
        return {relative: (root / relative).read_bytes() for relative in CONTRACT["candidateBindings"]}

    def test_current_binding_advance_preserves_original_header_witness(self):
        program = CONTRACT["baseline"]["programPath"]
        converter = "Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderFileMetadataRequestJsonConverter.cs"
        previous = CONTRACT["previousCandidateBindings"]
        self.assertEqual(5, len(previous))
        retained_supplier = CONTRACT["previousIgnoredSupplierCandidateBindings"]
        self.assertEqual(8, len(retained_supplier))
        self.assertNotEqual(previous[program], RED.binding_digest(retained_supplier[program]))
        supplier = "Legacy.Maliev.ProcurementService.Api/Serialization/SupplierIgnoredIdJsonConverter.cs"
        project = "Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj"
        self.assertEqual({converter, supplier, project}, set(retained_supplier) - set(previous))
        retained = CONTRACT["previousFileMetadataCandidateBindings"]
        self.assertEqual(6, len(retained))
        self.assertEqual({supplier, project}, set(retained_supplier) - set(retained))
        for relative in retained:
            if relative != program:
                self.assertEqual(retained[relative], RED.binding_digest(retained_supplier[relative]))
        for relative in previous:
            if relative != program:
                self.assertEqual(previous[relative], RED.binding_digest(retained_supplier[relative]))
        current = CONTRACT["candidateBindings"]
        metadata_identity = "Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementIgnoredBodyIdJsonOptions.cs"
        self.assertEqual(9, len(current))
        self.assertEqual({metadata_identity}, set(current) - set(retained_supplier))
        changed_header = RED.require_header_binding_advance(CONTRACT, RED.candidate_digests(CONTRACT))
        for relative in retained_supplier:
            if relative in changed_header:
                self.assertEqual(RED.binding_digest(retained_supplier[relative]),
                                 RED.binding_digest(CONTRACT["previousHeaderIgnoredFieldBindings"][relative]))
            elif relative in {program, converter}:
                self.assertNotEqual(RED.binding_digest(retained_supplier[relative]), RED.binding_digest(current[relative]))
            else:
                self.assertEqual(RED.binding_digest(retained_supplier[relative]), RED.binding_digest(current[relative]))
        self.assertEqual("19d17888cd77004b42f290a3c0daad454dfd4b5e", CONTRACT["baseline"]["programBlob"])
        self.assertEqual("afa62156da9a55476326bd9bfe1295a345f6fed72bfaaa437a5427ca93cbfef7", CONTRACT["baseline"]["programSha256"])
        sources = self.sources()
        with mock.patch.object(RED, "git", side_effect=lambda root, command, binding: sources[binding.removeprefix("HEAD:")]):
            self.assertEqual(sources, RED.candidate_sources(Path("."), CONTRACT))

    def test_each_current_candidate_binding_drift_is_rejected(self):
        sources = self.sources()
        for relative in sources:
            with self.subTest(relative=relative):
                mutated = dict(sources)
                mutated[relative] += b"source drift"
                with mock.patch.object(RED, "git", side_effect=lambda root, command, binding: mutated[binding.removeprefix("HEAD:")]):
                    with self.assertRaisesRegex(ValueError, "Reviewed candidate HEAD source changed"):
                        RED.candidate_sources(Path("."), CONTRACT)

    def test_restoration_checks_new_converter_and_all_other_retained_inputs(self):
        sources = self.sources()
        replaced = {CONTRACT["baseline"]["programPath"], CONTRACT["baseline"]["absentPath"]}
        for changed in (None, *(relative for relative in sources if relative not in replaced)):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                evidence = root / "evidence"
                evidence.mkdir()
                for relative, data in sources.items():
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                (root / CONTRACT["baseline"]["programPath"]).write_bytes(b"synthetic baseline replacement")
                (root / CONTRACT["baseline"]["absentPath"]).unlink()
                if changed is not None:
                    (root / changed).write_bytes(sources[changed] + b"source drift")
                with mock.patch.object(RED, "settle_command_groups") as settle, \
                        mock.patch.object(RED, "git", side_effect=lambda root, *args: b"synthetic-head" if args == ("rev-parse", "HEAD") else b""):
                    if changed is None:
                        RED.restore(root, CONTRACT, sources, evidence, "synthetic-head")
                        receipt = json.loads((evidence / "restoration.json").read_text(encoding="utf-8"))
                        self.assertEqual(CONTRACT["candidateBindings"], receipt["restored"])
                        self.assertTrue(receipt["trackedClean"])
                        for relative, data in sources.items():
                            self.assertEqual(data, (root / relative).read_bytes())
                    else:
                        with self.assertRaisesRegex(ValueError, "Candidate restoration mismatch"):
                            RED.restore(root, CONTRACT, sources, evidence, "synthetic-head")
                        self.assertFalse((evidence / "restoration.json").exists())
                    settle.assert_called_once_with(evidence)



class TypedCandidateProvenanceControls(unittest.TestCase):
    def test_explicit_digest_records_reject_scalar_extra_or_wrong_algorithm(self):
        for record in CONTRACT["candidateBindings"].values():
            self.assertEqual(record["sha256"], RED.binding_digest(record))
            for invalid in (record["sha256"], None, {}, {"gitBlob": "a" * 40},
                            {"sha256": record["sha256"], "extra": True},
                            {"sha256": "a" * 63}, {"sha256": "G" * 64},
                            {"sha256": record["sha256"].upper()}, {"sha256": 7}):
                with self.subTest(invalid_type=type(invalid).__name__), self.assertRaises(ValueError):
                    RED.binding_digest(invalid)

    def test_missing_format_or_wrong_current_roster_is_refused(self):
        import copy
        for mutation in ("missing-format", "wrong-format", "missing-record", "extra-record"):
            changed = copy.deepcopy(CONTRACT)
            if mutation == "missing-format":
                del changed["candidateBindingFormat"]
            elif mutation == "wrong-format":
                changed["candidateBindingFormat"] = "unreviewed"
            elif mutation == "missing-record":
                changed["candidateBindings"].pop(next(iter(changed["candidateBindings"])))
            else:
                changed["candidateBindings"]["unreviewed"] = {"sha256": "a" * 64}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                RED.candidate_digests(changed)

    def test_exact_header_successor_rejects_every_preimage_postimage_and_unrelated_drift(self):
        import copy
        current = RED.candidate_digests(CONTRACT)
        RED.require_header_binding_advance(CONTRACT, current)
        for section in ("preimages", "postimages"):
            for path in CONTRACT["headerIgnoredFieldBindingAdvance"][section]:
                changed = copy.deepcopy(CONTRACT)
                changed["headerIgnoredFieldBindingAdvance"][section][path] = {"sha256":"0"*64}
                with self.subTest(section=section,path=path), self.assertRaises(ValueError):
                    RED.require_header_binding_advance(changed, current)
        for path in current:
            changed = dict(current)
            changed[path] = "0"*64
            with self.subTest(path=path), self.assertRaises(ValueError):
                RED.require_header_binding_advance(CONTRACT, changed)

    def test_header_successor_requires_closed_two_binding_roster_format_and_generation(self):
        import copy
        for mutation in ("missing", "extra", "format", "issue", "base", "scalar"):
            changed = copy.deepcopy(CONTRACT)
            advance = changed["headerIgnoredFieldBindingAdvance"]
            if mutation == "missing": advance["postimages"].pop(next(iter(advance["postimages"])))
            elif mutation == "extra": advance["postimages"]["foreign"] = {"sha256":"0"*64}
            elif mutation == "format": advance["bindingFormat"] = "git-blob-record-v1"
            elif mutation == "issue": advance["issue"] = 68
            elif mutation == "base": advance["base"] = "main"
            else:
                path = next(iter(advance["preimages"]))
                advance["preimages"][path] = advance["preimages"][path]["sha256"]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                RED.candidate_digests(changed)


class SupplierAuditCandidateCustodyControls(unittest.TestCase):
    def test_supplier_audit_successor_retains_previous_header_witness_and_exact_third_delta(self):
        old = {path: RED.binding_digest(record) for path,record in CONTRACT["previousSupplierAuditCandidateBindings"].items()}
        header = RED.require_previous_header_binding_advance(CONTRACT, old)
        current = {path: RED.binding_digest(record) for path,record in CONTRACT["previousMetadataAuditCandidateBindings"].items()}
        supplier = "Legacy.Maliev.ProcurementService.Api/Serialization/SupplierIgnoredIdJsonConverter.cs"
        self.assertEqual({supplier},{path for path in current if current[path] != old[path]})
        self.assertEqual(header | {supplier}, RED.require_previous_supplier_audit_binding_advance(CONTRACT,current))

    def test_supplier_audit_binding_rejects_every_custody_preimage_postimage_and_roster_drift(self):
        import copy
        current = RED.candidate_digests(CONTRACT)
        for field in ("issue","base","bindingFormat"):
            changed = copy.deepcopy(CONTRACT)
            changed["supplierAuditBindingAdvance"][field] = "drift"
            with self.subTest(field=field),self.assertRaises(ValueError):
                RED.require_header_binding_advance(changed,current)
        for section in ("preimages","postimages"):
            for mutation in ("missing","extra","wrong","scalar"):
                changed = copy.deepcopy(CONTRACT)
                binding = changed["supplierAuditBindingAdvance"][section]
                path = next(iter(binding))
                if mutation == "missing": binding.pop(path)
                elif mutation == "extra": binding["foreign"] = {"sha256":"0"*64}
                elif mutation == "wrong": binding[path] = {"sha256":"0"*64}
                else: binding[path] = binding[path]["sha256"]
                with self.subTest(section=section,mutation=mutation),self.assertRaises(ValueError):
                    RED.require_header_binding_advance(changed,current)
        for path in current:
            changed = copy.deepcopy(CONTRACT)
            changed["previousSupplierAuditCandidateBindings"][path] = {"sha256":"0"*64}
            with self.subTest(path=path),self.assertRaises(ValueError):
                RED.require_header_binding_advance(changed,current)


class MetadataAuditCandidateCustodyControls(unittest.TestCase):
    def test_metadata_audit_successor_retains_previous_supplier_witness_and_exact_fourth_delta(self):
        old = {path: RED.binding_digest(record) for path,record in CONTRACT["previousMetadataAuditCandidateBindings"].items()}
        previous = RED.require_previous_supplier_audit_binding_advance(CONTRACT, old)
        current = RED.candidate_digests(CONTRACT)
        metadata = "Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementIgnoredBodyIdJsonOptions.cs"
        self.assertEqual({metadata},{path for path in current if current[path] != old[path]})
        self.assertEqual(previous | {metadata}, RED.require_header_binding_advance(CONTRACT,current))

    def test_metadata_audit_binding_rejects_every_custody_preimage_postimage_and_roster_drift(self):
        import copy
        current = RED.candidate_digests(CONTRACT)
        for field in ("issue","base","bindingFormat"):
            changed = copy.deepcopy(CONTRACT)
            changed["metadataAuditBindingAdvance"][field] = "drift"
            with self.subTest(field=field),self.assertRaises(ValueError):
                RED.require_header_binding_advance(changed,current)
        for section in ("preimages","postimages"):
            for mutation in ("missing","extra","wrong","scalar"):
                changed = copy.deepcopy(CONTRACT)
                binding = changed["metadataAuditBindingAdvance"][section]
                path = next(iter(binding))
                if mutation == "missing": binding.pop(path)
                elif mutation == "extra": binding["foreign"] = {"sha256":"0"*64}
                elif mutation == "wrong": binding[path] = {"sha256":"0"*64}
                else: binding[path] = binding[path]["sha256"]
                with self.subTest(section=section,mutation=mutation),self.assertRaises(ValueError):
                    RED.require_header_binding_advance(changed,current)
        for path in current:
            changed = copy.deepcopy(CONTRACT)
            changed["previousMetadataAuditCandidateBindings"][path] = {"sha256":"0"*64}
            with self.subTest(path=path),self.assertRaises(ValueError):
                RED.require_header_binding_advance(changed,current)


if __name__ == "__main__":
    unittest.main()
