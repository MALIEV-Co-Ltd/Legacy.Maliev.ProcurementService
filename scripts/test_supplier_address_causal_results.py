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
                    message = 'System.Text.Json.JsonException : The JSON value could not be converted to System.String.'
                else:
                    status = 'NotFound' if case['method'].startswith('MissingOwnerOrAddress_') else ('NoContent' if 'update: True' in case['name'] else 'Created')
                    message = 'Assert.Equal() Failure\nExpected: '+status+'\nActual:   BadRequest'
                ET.SubElement(error, 'Message').text = message
                ET.SubElement(error, 'StackTrace').text = 'at Frozen.'+case['method']+'()'
        (self.root/'coverage.cobertura.xml').write_text('<coverage><packages><package><classes><class><lines><line number="1" hits="1" /></lines></class></classes></package></packages></coverage>')
        return doc

    def run_guard(self, doc, phase='candidate', exit_code=None):
        ET.ElementTree(doc).write(self.root/'results.trx', encoding='utf-8')
        return guard.verify(self.root, self.manifest, phase, (1 if phase == 'baseline' else 0) if exit_code is None else exit_code)

    def test_candidate_positive(self):
        self.assertEqual(33, self.run_guard(self.fixture())['passed'])

    def test_baseline_positive(self):
        self.assertEqual(13, self.run_guard(self.fixture('baseline'), 'baseline')['failed'])

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
