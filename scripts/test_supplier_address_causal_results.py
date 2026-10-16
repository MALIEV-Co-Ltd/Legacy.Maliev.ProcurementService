import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location('causal', pathlib.Path(__file__).with_name('verify-supplier-address-causal-results.py'))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
MANIFEST = json.loads((pathlib.Path(__file__).parents[1] / 'docs' / 'procurement-supplier-address-causal-contract.json').read_text(encoding='utf-8'))
ACTUAL_CONVERTER_MESSAGE = "System.Text.Json.JsonException : The JSON value could not be converted to Legacy.Maliev.ProcurementService.Application.Models.UpsertSupplierAddressRequest. Path: $.Building | LineNumber: 0 | BytePositionInLine: 22.\n---- System.InvalidOperationException : Cannot get the value of a token type 'Number' as a string."
ACTUAL_CONVERTER_STACK = 'at Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementSupplierAddressScalarStringTests.Converter_IsAddressRequestLocal_AndWritesStringsWithoutChangingCountry() in /fixture/ProcurementSupplierAddressScalarStringTests.cs:line 213\n at System.Text.Json.ThrowHelper.ThrowInvalidOperationException_ExpectedString(JsonTokenType tokenType)\n at System.Text.Json.Serialization.Converters.StringConverter.Read(Utf8JsonReader& reader, Type typeToConvert, JsonSerializerOptions options)'


OBSERVED_CONVERTER_ROW = {
    "outcome": "Failed",
    "counters": "<Counters total=\"33\" executed=\"33\" passed=\"20\" failed=\"13\" error=\"0\" timeout=\"0\" aborted=\"0\" inconclusive=\"0\" passedButRunAborted=\"0\" notRunnable=\"0\" notExecuted=\"0\" disconnected=\"0\" warning=\"0\" completed=\"0\" inProgress=\"0\" pending=\"0\" xmlns=\"http://microsoft.com/schemas/VisualStudio/TeamTest/2010\" />",
    "stack": "   at System.Text.Json.ThrowHelper.ReThrowWithPath(ReadStack& state, Utf8JsonReader& reader, Exception ex)\n   at System.Text.Json.Serialization.JsonConverter`1.ReadCore(Utf8JsonReader& reader, T& value, JsonSerializerOptions options, ReadStack& state)\n   at System.Text.Json.Serialization.Metadata.JsonTypeInfo`1.Deserialize(Utf8JsonReader& reader, ReadStack& state)\n   at System.Text.Json.JsonSerializer.ReadFromSpan[TValue](ReadOnlySpan`1 utf8Json, JsonTypeInfo`1 jsonTypeInfo, Nullable`1 actualByteCount)\n   at System.Text.Json.JsonSerializer.ReadFromSpan[TValue](ReadOnlySpan`1 json, JsonTypeInfo`1 jsonTypeInfo)\n   at Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementSupplierAddressScalarStringTests.Converter_IsAddressRequestLocal_AndWritesStringsWithoutChangingCountry() in /home/runner/work/Legacy.Maliev.ProcurementService/Legacy.Maliev.ProcurementService/.address-baseline/Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierAddressScalarStringTests.cs:line 213\n   at System.Reflection.MethodBaseInvoker.InterpretedInvoke_Method(Object obj, IntPtr* args)\n   at System.Reflection.MethodBaseInvoker.InvokeWithNoArgs(Object obj, BindingFlags invokeAttr)\n----- Inner Stack Trace -----\n   at System.Text.Json.ThrowHelper.ThrowInvalidOperationException_ExpectedString(JsonTokenType tokenType)\n   at System.Text.Json.Utf8JsonReader.GetString()\n   at System.Text.Json.Serialization.JsonConverter`1.TryRead(Utf8JsonReader& reader, Type typeToConvert, JsonSerializerOptions options, ReadStack& state, T& value, Boolean& isPopulatedValue)\n   at System.Text.Json.Serialization.JsonConverter`1.TryReadAsObject(Utf8JsonReader& reader, Type typeToConvert, JsonSerializerOptions options, ReadStack& state, Object& value)\n   at System.Text.Json.Serialization.Converters.LargeObjectWithParameterizedConstructorConverter`1.ReadAndCacheConstructorArgument(ReadStack& state, Utf8JsonReader& reader, JsonParameterInfo jsonParameterInfo)\n   at System.Text.Json.Serialization.Converters.ObjectWithParameterizedConstructorConverter`1.OnTryRead(Utf8JsonReader& reader, Type typeToConvert, JsonSerializerOptions options, ReadStack& state, T& value)\n   at System.Text.Json.Serialization.JsonConverter`1.TryRead(Utf8JsonReader& reader, Type typeToConvert, JsonSerializerOptions options, ReadStack& state, T& value, Boolean& isPopulatedValue)\n   at System.Text.Json.Serialization.JsonConverter`1.ReadCore(Utf8JsonReader& reader, T& value, JsonSerializerOptions options, ReadStack& state)",
    "error": "System.Text.Json.JsonException : The JSON value could not be converted to Legacy.Maliev.ProcurementService.Application.Models.UpsertSupplierAddressRequest. Path: $.Building | LineNumber: 0 | BytePositionInLine: 22.\n---- System.InvalidOperationException : Cannot get the value of a token type 'Number' as a string.",
    "name": "Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementSupplierAddressScalarStringTests.Converter_IsAddressRequestLocal_AndWritesStringsWithoutChangingCountry",
    "path": "baseline/_runnervm8k3b6_2026-10-16_06_31_52_net10.0.trx"
}

SHORT_OBSERVED_CONVERTER_ROW = {
    "artifact": 12030477742,
    "sha256": "7d4ea799db32fbfdfbeaff984e53a9116b22090987f6a116d6b9ec17db4e866a",
    "path": "baseline/_runnervm8k3b6_2026-10-16_06_58_36_net10.0.trx",
    "name": "Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementSupplierAddressScalarStringTests.Converter_IsAddressRequestLocal_AndWritesStringsWithoutChangingCountry",
    "outcome": "Failed",
    "error": "System.Text.Json.JsonException : The JSON value could not be converted to Legacy.Maliev.ProcurementService.Application.Models.UpsertSupplierAddressRequest. Path: $.Building | LineNumber: 0 | BytePositionInLine: 22.\n---- System.InvalidOperationException : Cannot get the value of a token type 'Number' as a string.",
    "stack": "   at System.Text.Json.ThrowHelper.ReThrowWithPath(ReadStack& state, Utf8JsonReader& reader, Exception ex)\n   at System.Text.Json.Serialization.JsonConverter`1.ReadCore(Utf8JsonReader& reader, T& value, JsonSerializerOptions options, ReadStack& state)\n   at System.Text.Json.JsonSerializer.ReadFromSpan[TValue](ReadOnlySpan`1 utf8Json, JsonTypeInfo`1 jsonTypeInfo, Nullable`1 actualByteCount)\n   at System.Text.Json.JsonSerializer.ReadFromSpan[TValue](ReadOnlySpan`1 json, JsonTypeInfo`1 jsonTypeInfo)\n   at Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementSupplierAddressScalarStringTests.Converter_IsAddressRequestLocal_AndWritesStringsWithoutChangingCountry() in /home/runner/work/Legacy.Maliev.ProcurementService/Legacy.Maliev.ProcurementService/.address-baseline/Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierAddressScalarStringTests.cs:line 213\n   at System.Reflection.MethodBaseInvoker.InterpretedInvoke_Method(Object obj, IntPtr* args)\n   at System.Reflection.MethodBaseInvoker.InvokeWithNoArgs(Object obj, BindingFlags invokeAttr)\n----- Inner Stack Trace -----\n   at System.Text.Json.ThrowHelper.ThrowInvalidOperationException_ExpectedString(JsonTokenType tokenType)\n   at System.Text.Json.Utf8JsonReader.GetString()\n   at System.Text.Json.Serialization.JsonConverter`1.TryRead(Utf8JsonReader& reader, Type typeToConvert, JsonSerializerOptions options, ReadStack& state, T& value, Boolean& isPopulatedValue)\n   at System.Text.Json.Serialization.JsonConverter`1.TryReadAsObject(Utf8JsonReader& reader, Type typeToConvert, JsonSerializerOptions options, ReadStack& state, Object& value)\n   at System.Text.Json.Serialization.Converters.LargeObjectWithParameterizedConstructorConverter`1.ReadAndCacheConstructorArgument(ReadStack& state, Utf8JsonReader& reader, JsonParameterInfo jsonParameterInfo)\n   at System.Text.Json.Serialization.Converters.ObjectWithParameterizedConstructorConverter`1.OnTryRead(Utf8JsonReader& reader, Type typeToConvert, JsonSerializerOptions options, ReadStack& state, T& value)\n   at System.Text.Json.Serialization.JsonConverter`1.ReadCore(Utf8JsonReader& reader, T& value, JsonSerializerOptions options, ReadStack& state)",
    "counters": "<Counters total=\"33\" executed=\"33\" passed=\"20\" failed=\"13\" error=\"0\" timeout=\"0\" aborted=\"0\" inconclusive=\"0\" passedButRunAborted=\"0\" notRunnable=\"0\" notExecuted=\"0\" disconnected=\"0\" warning=\"0\" completed=\"0\" inProgress=\"0\" pending=\"0\" xmlns=\"http://microsoft.com/schemas/VisualStudio/TeamTest/2010\" />"
}

class CausalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.manifest = copy.deepcopy(MANIFEST)

    def fixture(self, phase='candidate'):
        doc = ET.Element('TestRun')
        definitions = ET.SubElement(doc, 'TestDefinitions')
        entries = ET.SubElement(doc, 'TestEntries')
        results = ET.SubElement(doc, 'Results')
        counters = dict(total='33', executed='33', passed='20' if phase == 'baseline' else '33', failed='13' if phase == 'baseline' else '0')
        counters.update({key:'0' for key in ('error','timeout','aborted','inconclusive','passedButRunAborted','notRunnable','notExecuted','disconnected','warning','completed','inProgress','pending')})
        ET.SubElement(ET.SubElement(doc, 'ResultSummary', outcome='Failed' if phase == 'baseline' else 'Completed'), 'Counters', counters)
        for case in self.manifest['cases']:
            execution = str(uuid.uuid4())
            definition = ET.SubElement(definitions, 'UnitTest', id=case['testId'], name=case['name'])
            ET.SubElement(definition, 'Execution', id=execution)
            ET.SubElement(definition, 'TestMethod', name=case['method'], className='Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementSupplierAddressScalarStringTests')
            ET.SubElement(entries, 'TestEntry', testId=case['testId'], executionId=execution)
            row = ET.SubElement(results, 'UnitTestResult', testId=case['testId'], executionId=execution, testName=case['name'], outcome=case[phase+'Outcome'])
            if row.get('outcome') == 'Failed':
                error = ET.SubElement(ET.SubElement(row, 'Output'), 'ErrorInfo')
                if case['method'].startswith('Converter_'):
                    message = ACTUAL_CONVERTER_MESSAGE
                else:
                    status = 'NotFound' if case['method'].startswith('MissingOwnerOrAddress_') else ('NoContent' if 'update: True' in case['name'] else 'Created')
                    message = 'Assert.Equal() Failure\nExpected: '+status+'\nActual:   BadRequest'
                ET.SubElement(error, 'Message').text = message
                ET.SubElement(error, 'StackTrace').text = ACTUAL_CONVERTER_STACK if case['method'].startswith('Converter_') else 'at Frozen.'+case['method']+'()'
        (self.root/'coverage.cobertura.xml').write_text('<coverage><packages><package><classes><class><lines><line number="1" hits="1" /></lines></class></classes></package></packages></coverage>')
        return doc

    def run_guard(self, doc, phase='candidate', exit_code=None):
        ET.ElementTree(doc).write(self.root/'results.trx', encoding='utf-8')
        return guard.verify(self.root, self.manifest, phase, (1 if phase == 'baseline' else 0) if exit_code is None else exit_code)

    def test_candidate_positive(self):
        self.assertEqual(33, self.run_guard(self.fixture())['passed'])

    def test_baseline_positive(self):
        self.assertEqual(13, self.run_guard(self.fixture('baseline'), 'baseline')['failed'])

    def test_authentic_baseline_numeric_string_failure(self):
        doc=self.fixture('baseline')
        error=doc.find('.//ErrorInfo')
        error.find('Message').text=ACTUAL_CONVERTER_MESSAGE
        error.find('StackTrace').text=ACTUAL_CONVERTER_STACK
        self.assertEqual(13,self.run_guard(doc,'baseline')['failed'])

    def test_unrelated_converter_failures_refused(self):
        for before,after in [('UpsertSupplierAddressRequest','UpsertPurchaseOrderRequest'),('$.Building','$.CountryId'),("'Number'","'StartObject'"),('System.InvalidOperationException','System.IO.IOException')]:
            with self.subTest(before=before):
                doc=self.fixture('baseline');doc.find('.//ErrorInfo/Message').text=ACTUAL_CONVERTER_MESSAGE.replace(before,after)
                with self.assertRaises(ValueError):self.run_guard(doc,'baseline')

    def test_unrelated_converter_stack_refused(self):
        for before,after in [('line 213','line 212'),('StringConverter.Read(','ObjectConverter.Read('),('ThrowInvalidOperationException_ExpectedString(','Fixture.InitializeAsync(')]:
            with self.subTest(before=before):
                doc=self.fixture('baseline');doc.find('.//ErrorInfo/StackTrace').text=ACTUAL_CONVERTER_STACK.replace(before,after)
                with self.assertRaises(ValueError):self.run_guard(doc,'baseline')

    def observed_baseline(self, observed=OBSERVED_CONVERTER_ROW):
        doc = self.fixture('baseline')
        row = next(x for x in doc.findall('./Results/UnitTestResult')
                   if x.get('testName') == observed['name'])
        self.assertEqual(observed['outcome'], row.get('outcome'))
        error = row.find('./Output/ErrorInfo')
        error.find('Message').text = observed['error']
        error.find('StackTrace').text = observed['stack']
        return doc, error

    def test_observed_parameterized_string_stack_positive(self):
        # Exact PII-free hosted row from38861609108/job116844927031; no JIT-cause claim.
        doc, _ = self.observed_baseline()
        proof = self.run_guard(doc, 'baseline')
        self.assertEqual((20, 13, 0), (proof['passed'], proof['failed'], proof['skipped']))
        self.assertFalse(proof['fullSuiteAcceptance'])
        self.assertFalse(proof['providerDisposalAcceptance'])
        self.assertFalse(proof['productionEnrollmentProven'])

    def test_observed_wrong_caller_or_source_line_refused(self):
        for before, after in [
            ('ProcurementSupplierAddressScalarStringTests.Converter_', 'ForeignTests.Converter_'),
            ('Legacy.Maliev.ProcurementService.Tests.Integration.', 'Foreign.Namespace.'),
            ('Converter_IsAddressRequestLocal_AndWritesStringsWithoutChangingCountry()', 'InitializeAsync()'),
            ('ProcurementSupplierAddressScalarStringTests.cs:line 213', 'ForeignTests.cs:line 213'),
            ('line 213', 'line 212'),
            ('line 213', 'line 2130'),
        ]:
            with self.subTest(before=before, after=after):
                doc, error = self.observed_baseline()
                error.find('StackTrace').text = OBSERVED_CONVERTER_ROW['stack'].replace(before, after)
                with self.assertRaises(ValueError):
                    self.run_guard(doc, 'baseline')

    def test_observed_wrong_error_token_path_or_position_refused(self):
        for before, after in [
            ('System.Text.Json.JsonException', 'System.IO.IOException'),
            ('UpsertSupplierAddressRequest', 'UpsertPurchaseOrderRequest'),
            ('$.Building', '$.CountryId'),
            ('LineNumber: 0', 'LineNumber: 1'),
            ('BytePositionInLine: 22', 'BytePositionInLine: 23'),
            ('System.InvalidOperationException', 'System.IO.IOException'),
            ("'Number'", "'StartObject'"),
            ("'Number'", "'Boolean'"),
            ('as a string.', 'as an integer.'),
        ]:
            with self.subTest(before=before, after=after):
                doc, error = self.observed_baseline()
                error.find('Message').text = OBSERVED_CONVERTER_ROW['error'].replace(before, after)
                with self.assertRaises(ValueError):
                    self.run_guard(doc, 'baseline')

    def test_observed_requires_each_exact_typed_reader_frame(self):
        frames = OBSERVED_CONVERTER_ROW['stack'].splitlines()
        for index in range(len(frames)):
            if index in (2, 15):
                continue  # Only the two reviewed optional framework positions.
            with self.subTest(removed_frame=index):
                doc, error = self.observed_baseline()
                error.find('StackTrace').text = '\n'.join(frames[:index] + frames[index + 1:])
                with self.assertRaises(ValueError):
                    self.run_guard(doc, 'baseline')
        for before, after in [
            ('Utf8JsonReader.GetString()', 'Utf8JsonReader.GetInt32()'),
            ('JsonConverter`1.TryRead(', 'JsonConverter`1.Read('),
            ('JsonConverter`1.TryReadAsObject(', 'ObjectConverter.Read('),
            ('ReadAndCacheConstructorArgument(', 'ReadConstructorArguments('),
            ('ObjectWithParameterizedConstructorConverter`1.OnTryRead(', 'ObjectDefaultConverter`1.OnTryRead('),
            ('ThrowInvalidOperationException_ExpectedString(', 'ThrowJsonReaderException('),
        ]:
            with self.subTest(reader=before):
                doc, error = self.observed_baseline()
                error.find('StackTrace').text = OBSERVED_CONVERTER_ROW['stack'].replace(before, after)
                with self.assertRaises(ValueError):
                    self.run_guard(doc, 'baseline')

    def test_observed_infrastructure_and_extra_frames_refused(self):
        for stack in [
            'at Testcontainers.Container.StartAsync()\n' + OBSERVED_CONVERTER_ROW['stack'],
            OBSERVED_CONVERTER_ROW['stack'] + '\n at Fixture.InitializeAsync()',
            OBSERVED_CONVERTER_ROW['stack'].replace('at System.Text.Json.Utf8JsonReader.GetString()', 'at Testcontainers.Container.StartAsync()'),
        ]:
            with self.subTest(stack=stack):
                doc, error = self.observed_baseline()
                error.find('StackTrace').text = stack
                with self.assertRaises(ValueError):
                    self.run_guard(doc, 'baseline')

    def test_observed_alternative_keeps_outer_evidence_guards(self):
        for mutation in ('roster', 'counters', 'execution', 'identity', 'entry', 'timestamp', 'coverage'):
            with self.subTest(mutation=mutation):
                doc, _ = self.observed_baseline()
                if mutation == 'roster':
                    results = doc.find('Results')
                    results.remove(results[-1])
                elif mutation == 'counters':
                    doc.find('./ResultSummary/Counters').set('failed', '12')
                elif mutation == 'execution':
                    doc.find('./Results/UnitTestResult').set('executionId', 'INVALID')
                elif mutation == 'identity':
                    doc.find('./Results/UnitTestResult').set('testId', str(uuid.uuid4()))
                elif mutation == 'entry':
                    doc.find('./TestEntries/TestEntry').set('executionId', str(uuid.uuid4()))
                elif mutation == 'timestamp':
                    self.diagnostics(doc)[0].set('timestamp', '2026-10-16T06:31:52')
                else:
                    (self.root/'coverage.cobertura.xml').write_text('<coverage />')
                with self.assertRaises(ValueError):
                    self.run_guard(doc, 'baseline')


    def test_four_reviewed_frame_shapes_positive(self):
        long_row = copy.deepcopy(OBSERVED_CONVERTER_ROW)
        short_row = copy.deepcopy(SHORT_OBSERVED_CONVERTER_ROW)
        self.assertEqual(17, len(long_row['stack'].splitlines()))
        self.assertEqual(15, len(short_row['stack'].splitlines()))
        outer = long_row['stack'].splitlines()[2]
        inner = long_row['stack'].splitlines()[15]
        outer_only = copy.deepcopy(short_row)
        frames = short_row['stack'].splitlines()
        outer_only['stack'] = '\n'.join(frames[:2] + [outer] + frames[2:])
        inner_only = copy.deepcopy(short_row)
        # Insert directly after OnTryRead and before the final ReadCore.
        inner_only['stack'] = '\n'.join(frames[:-1] + [inner] + frames[-1:])
        for shape, observed in [('both', long_row), ('neither', short_row),
                                ('outer-only', outer_only), ('inner-only', inner_only)]:
            with self.subTest(shape=shape):
                doc, _ = self.observed_baseline(observed)
                proof = self.run_guard(doc, 'baseline')
                self.assertEqual((20, 13, 0), (proof['passed'], proof['failed'], proof['skipped']))
                self.assertFalse(proof['fullSuiteAcceptance'])
                self.assertFalse(proof['providerDisposalAcceptance'])
                self.assertFalse(proof['productionEnrollmentProven'])

    def test_short_observed_shape_requires_every_remaining_frame(self):
        frames = SHORT_OBSERVED_CONVERTER_ROW['stack'].splitlines()
        for index in range(len(frames)):
            with self.subTest(removed_required=index):
                doc, error = self.observed_baseline(SHORT_OBSERVED_CONVERTER_ROW)
                error.find('StackTrace').text = '\n'.join(frames[:index] + frames[index + 1:])
                with self.assertRaises(ValueError):
                    self.run_guard(doc, 'baseline')

    def test_required_frame_reordering_is_refused_in_both_observed_shapes(self):
        for observed in (OBSERVED_CONVERTER_ROW, SHORT_OBSERVED_CONVERTER_ROW):
            frames = observed['stack'].splitlines()
            for first, second in [(0, 1), (9, 10)]:
                with self.subTest(size=len(frames), swapped=(first, second)):
                    changed = list(frames)
                    changed[first], changed[second] = changed[second], changed[first]
                    doc, error = self.observed_baseline(observed)
                    error.find('StackTrace').text = '\n'.join(changed)
                    with self.assertRaises(ValueError):
                        self.run_guard(doc, 'baseline')

    def test_optional_frames_cannot_be_substituted_duplicated_or_moved(self):
        long_frames = OBSERVED_CONVERTER_ROW['stack'].splitlines()
        short_frames = SHORT_OBSERVED_CONVERTER_ROW['stack'].splitlines()
        for index in (2, 15):
            for mutation in ('substitute', 'duplicate', 'move', 'wrong-short-position'):
                with self.subTest(optional=index, mutation=mutation):
                    frames = list(long_frames)
                    if mutation == 'substitute':
                        frames[index] = frames[index].replace('System.Text.Json.', 'Foreign.Reader.')
                    elif mutation == 'duplicate':
                        frames.insert(index, frames[index])
                    elif mutation == 'move':
                        frames.insert(0, frames.pop(index))
                    else:
                        frames = [long_frames[index]] + short_frames
                    doc, error = self.observed_baseline()
                    error.find('StackTrace').text = '\n'.join(frames)
                    with self.assertRaises(ValueError):
                        self.run_guard(doc, 'baseline')


    def diagnostics(self, doc):
        infos = ET.SubElement(doc.find('ResultSummary'), 'RunInfos')
        for case in self.manifest['cases']:
            if case['baselineOutcome'] == 'Failed':
                info = ET.SubElement(infos, 'RunInfo', computerName='runnervmmprz5', outcome='Error', timestamp='2026-10-11T02:11:14.0887522+00:00')
                ET.SubElement(info, 'Text').text = '[xUnit.net 00:00:00.70]     '+case['name']+' [FAIL]'
        return infos

    def test_baseline_assertion_diagnostics_positive(self):
        # Metadata/text shape from authentic File125 baseline TRX.
        doc=self.fixture('baseline');self.diagnostics(doc)
        self.assertEqual(13,len(self.run_guard(doc,'baseline')['baselineAssertionDiagnostics']))

    def test_candidate_assertion_diagnostics_refused(self):
        doc=self.fixture();self.diagnostics(doc)
        with self.assertRaises(ValueError):self.run_guard(doc)

    def test_missing_assertion_diagnostic_refused(self):
        doc=self.fixture('baseline');infos=self.diagnostics(doc);infos.remove(infos[0])
        with self.assertRaises(ValueError):self.run_guard(doc,'baseline')

    def test_duplicate_assertion_diagnostic_refused(self):
        doc=self.fixture('baseline');infos=self.diagnostics(doc);infos.append(copy.deepcopy(infos[0]))
        with self.assertRaises(ValueError):self.run_guard(doc,'baseline')

    def test_unmapped_assertion_diagnostic_refused(self):
        doc=self.fixture('baseline');infos=self.diagnostics(doc);infos[0].find('Text').text='[xUnit.net 00:00:00.70]     Foreign.Test [FAIL]'
        with self.assertRaises(ValueError):self.run_guard(doc,'baseline')

    def test_passing_case_assertion_diagnostic_refused(self):
        doc=self.fixture('baseline');infos=self.diagnostics(doc)
        case=next(x for x in self.manifest['cases'] if x['baselineOutcome']=='Passed')
        infos[0].find('Text').text='[xUnit.net 00:00:00.70]     '+case['name']+' [FAIL]'
        with self.assertRaises(ValueError):self.run_guard(doc,'baseline')

    def test_infrastructure_diagnostic_refused(self):
        doc=self.fixture('baseline');infos=self.diagnostics(doc);infos[0].find('Text').text='[xUnit.net 00:00:00.70] Fixture initialization failed'
        with self.assertRaises(ValueError):self.run_guard(doc,'baseline')

    def test_malformed_diagnostic_metadata_refused(self):
        for key,value in [('timestamp','invalid'),('timestamp','2026-10-11T02:11:14'),('outcome','Warning'),('computerName','')]:
            with self.subTest(key=key,value=value):
                doc=self.fixture('baseline');infos=self.diagnostics(doc);infos[0].set(key,value)
                with self.assertRaises(ValueError):self.run_guard(doc,'baseline')

    def test_malformed_diagnostic_content_refused(self):
        for mutation in ('duplicateText','extraChild','extraAttribute','nestedText','suffix'):
            with self.subTest(mutation=mutation):
                doc=self.fixture('baseline');infos=self.diagnostics(doc);info=infos[0]
                if mutation=='duplicateText':info.append(copy.deepcopy(info.find('Text')))
                elif mutation=='extraChild':ET.SubElement(info,'Foreign')
                elif mutation=='extraAttribute':info.set('foreign','1')
                elif mutation=='nestedText':ET.SubElement(info.find('Text'),'Foreign')
                else:info.find('Text').text+=' infrastructure failure'
                with self.assertRaises(ValueError):self.run_guard(doc,'baseline')

    def test_misplaced_diagnostic_refused(self):
        doc=self.fixture('baseline');infos=self.diagnostics(doc);doc.append(copy.deepcopy(infos[0]))
        with self.assertRaises(ValueError):self.run_guard(doc,'baseline')

    def test_wrong_process_exit(self):
        with self.assertRaises(ValueError): self.run_guard(self.fixture(), exit_code=1)

    def test_baseline_setup_failure_cannot_qualify(self):
        doc=self.fixture('baseline'); doc.find('.//ErrorInfo/Message').text='Fixture initialization failed'
        with self.assertRaises(ValueError): self.run_guard(doc,'baseline')

    def test_baseline_wrong_status_cannot_qualify(self):
        doc=self.fixture('baseline')
        for node in doc.findall('.//ErrorInfo/Message'):
            if 'BadRequest' in node.text: node.text=node.text.replace('BadRequest','InternalServerError'); break
        with self.assertRaises(ValueError): self.run_guard(doc,'baseline')

    def test_baseline_wrong_stack_cannot_qualify(self):
        doc=self.fixture('baseline'); doc.find('.//ErrorInfo/StackTrace').text='at InitializeAsync()'
        with self.assertRaises(ValueError): self.run_guard(doc,'baseline')

    def test_duplicate_execution(self):
        doc=self.fixture(); rows=doc.findall('./Results/UnitTestResult'); rows[1].set('executionId',rows[0].get('executionId'))
        with self.assertRaises(ValueError): self.run_guard(doc)

    def test_unknown_identity(self):
        doc=self.fixture(); doc.find('./Results/UnitTestResult').set('testId',str(uuid.uuid4()))
        with self.assertRaises(ValueError): self.run_guard(doc)

    def test_entry_mismatch(self):
        doc=self.fixture(); doc.find('./TestEntries/TestEntry').set('executionId',str(uuid.uuid4()))
        with self.assertRaises(ValueError): self.run_guard(doc)

    def test_missing_case(self):
        doc=self.fixture(); results=doc.find('Results'); results.remove(results[0])
        with self.assertRaises(ValueError): self.run_guard(doc)

    def test_noncanonical_execution(self):
        doc=self.fixture(); doc.find('./Results/UnitTestResult').set('executionId','invalid')
        with self.assertRaises(ValueError): self.run_guard(doc)

    def test_skipped_counter(self):
        doc=self.fixture(); doc.find('./ResultSummary/Counters').set('notExecuted','1')
        with self.assertRaises(ValueError): self.run_guard(doc)

    def test_passing_error(self):
        doc=self.fixture(); ET.SubElement(doc.find('./Results/UnitTestResult'),'ErrorInfo')
        with self.assertRaises(ValueError): self.run_guard(doc)

    def test_coverage_missing(self):
        doc=self.fixture(); (self.root/'coverage.cobertura.xml').unlink()
        with self.assertRaises(ValueError): self.run_guard(doc)

    def test_coverage_drift(self):
        doc=self.fixture(); other=self.root/'other'; other.mkdir(); (other/'coverage.cobertura.xml').write_text('<coverage />')
        with self.assertRaises(ValueError): self.run_guard(doc)

    def test_wrong_summary_outcome(self):
        doc=self.fixture();doc.find('ResultSummary').set('outcome','Failed')
        with self.assertRaises(ValueError):self.run_guard(doc)

    def test_duplicate_summary(self):
        doc=self.fixture();doc.append(copy.deepcopy(doc.find('ResultSummary')))
        with self.assertRaises(ValueError):self.run_guard(doc)

    def test_duplicate_counters(self):
        doc=self.fixture();summary=doc.find('ResultSummary');summary.append(copy.deepcopy(summary.find('Counters')))
        with self.assertRaises(ValueError):self.run_guard(doc)

    def test_runner_error_refused(self):
        doc=self.fixture('baseline');ET.SubElement(ET.SubElement(doc.find('ResultSummary'),'RunInfos'),'RunInfo',outcome='Error')
        with self.assertRaises(ValueError):self.run_guard(doc,'baseline')

    def test_duplicate_execution_node(self):
        doc=self.fixture();definition=doc.find('./TestDefinitions/UnitTest');definition.append(copy.deepcopy(definition.find('Execution')))
        with self.assertRaises(ValueError):self.run_guard(doc)

    def test_duplicate_method_node(self):
        doc=self.fixture();definition=doc.find('./TestDefinitions/UnitTest');definition.append(copy.deepcopy(definition.find('TestMethod')))
        with self.assertRaises(ValueError):self.run_guard(doc)

    def test_duplicate_error_message(self):
        doc=self.fixture('baseline');error=doc.find('.//ErrorInfo');error.append(copy.deepcopy(error.find('Message')))
        with self.assertRaises(ValueError):self.run_guard(doc,'baseline')

    def test_baseline_auth_refusal_cannot_qualify(self):
        doc=self.fixture('baseline')
        for node in doc.findall('.//ErrorInfo/Message'):
            if 'BadRequest' in node.text:node.text=node.text.replace('BadRequest','Forbidden');break
        with self.assertRaises(ValueError):self.run_guard(doc,'baseline')


if __name__ == '__main__':
    unittest.main()
