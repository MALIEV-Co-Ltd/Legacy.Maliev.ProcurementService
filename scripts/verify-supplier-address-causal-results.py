"""Verify frozen33 executions; infrastructure failure never qualifies baseline RED."""
import hashlib
import datetime
import json
import pathlib
import re
import sys
import uuid
import xml.etree.ElementTree as ET


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def one(node, path, message):
    nodes = node.findall(path)
    require(len(nodes) == 1, message)
    return nodes[0]


def verify(root, manifest, phase, exit_code):
    require(phase in ('baseline', 'candidate'), 'Unknown phase')
    require(exit_code == (1 if phase == 'baseline' else 0), 'Unexpected test process exit')
    cases = manifest['cases']
    expected = {(x['name'], x['testId']): x for x in cases}
    require(manifest['expectedCases'] == len(cases) == len(expected) == 33, 'Frozen roster must contain33 unique cases')
    require(all(canonical(x['testId']) for x in cases), 'Noncanonical frozen test GUID')
    require(sum(x['baselineOutcome'] == 'Failed' for x in cases) == 13, 'Baseline must declare13 failures')
    require(all(x['candidateOutcome'] == 'Passed' for x in cases), 'Candidate roster must require all passes')
    reports = list(root.rglob('*.trx'))
    require(len(reports) == 1, 'Require exactly one phase TRX')
    doc = ET.parse(reports[0])
    for path in ('./{*}TestDefinitions', './{*}TestEntries', './{*}Results'):
        one(doc, path, 'Require exactly one phase collection: ' + path)
    definitions = doc.findall('./{*}TestDefinitions/{*}UnitTest')
    entries = doc.findall('./{*}TestEntries/{*}TestEntry')
    results = doc.findall('./{*}Results/{*}UnitTestResult')
    require(len(definitions) == len(entries) == len(results) == 33, 'Require33 actual definitions, entries and results')
    defs = {x.get('id'): x for x in definitions}
    joins = {x.get('testId'): x.get('executionId') for x in entries}
    require(len(defs) == len(joins) == 33, 'Duplicate definition or entry')
    summary = one(doc, './{*}ResultSummary', 'Require exactly one phase summary')
    require(summary.get('outcome') == ('Failed' if phase == 'baseline' else 'Completed'), 'Unexpected phase summary outcome')
    require(len(summary.findall('./{*}RunInfos')) <= 1, 'Duplicate run diagnostics collection')
    run_infos = summary.findall('./{*}RunInfos/{*}RunInfo')
    collections = summary.findall('./{*}RunInfos')
    require(not collections or (not collections[0].attrib and len(collections[0]) == len(run_infos)), 'Unexpected run diagnostics collection content')
    require(len(doc.findall('.//{*}RunInfo')) == len(run_infos), 'Misplaced run diagnostic')
    require(phase == 'baseline' or not run_infos, 'Candidate run diagnostics forbidden')
    counters = one(summary, './{*}Counters', 'Require exactly one phase counter node')
    passed, failed = (20, 13) if phase == 'baseline' else (33, 0)
    for key, value in {'total':33, 'executed':33, 'passed':passed, 'failed':failed}.items():
        require(counters.get(key) == str(value), 'Unexpected phase counter: ' + key)
    for key in ('error', 'timeout', 'aborted', 'inconclusive', 'passedButRunAborted',
                'notRunnable', 'notExecuted', 'disconnected', 'warning', 'completed', 'inProgress', 'pending'):
        require(counters.get(key) == '0', 'Nonpassing counter: ' + key)
    actual = set()
    executions = set()
    failures = []
    for result in results:
        key = (result.get('testName'), result.get('testId'))
        execution = result.get('executionId')
        require(key in expected and key not in actual, 'Unknown or duplicate result identity')
        require(canonical(execution) and execution not in executions, 'Invalid or duplicate execution GUID')
        definition = defs.get(key[1])
        require(definition is not None and definition.get('name') == key[0], 'Unbound result definition')
        defined_execution = one(definition, './{*}Execution', 'Require exactly one definition execution')
        require(defined_execution.get('id') == execution == joins.get(key[1]), 'Definition/entry/result execution mismatch')
        method = one(definition, './{*}TestMethod', 'Require exactly one test method')
        case = expected[key]
        require(method.get('name') == case['method'] and method.get('className', '').split(',')[0] == 'Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementSupplierAddressScalarStringTests', 'Wrong test method/class')
        outcome = case[phase + 'Outcome']
        require(result.get('outcome') == outcome, 'Unexpected case outcome')
        errors = result.findall('.//{*}ErrorInfo')
        if outcome == 'Passed':
            require(not errors, 'Passing row contains failure evidence')
        else:
            require(len(errors) == 1, 'Baseline failure requires one actual error')
            message = one(errors[0], './{*}Message', 'Require one actual failure message').text or ''
            stack = one(errors[0], './{*}StackTrace', 'Require one actual failure stack').text or ''
            require(case['method'] in stack, 'Failure must originate in the frozen test method')
            if case['method'] == 'Converter_IsAddressRequestLocal_AndWritesStringsWithoutChangingCountry':
                require('System.Text.Json.JsonException' in message and 'System.String' in message, 'Expected local numeric-to-string deserialization failure')
            else:
                expected_status = 'NotFound' if case['method'].startswith('MissingOwnerOrAddress_') else ('NoContent' if 'update: True' in case['name'] else 'Created')
                require('Assert.Equal() Failure' in message and re.search(r'Expected:\s+' + expected_status + r'\b', message) and re.search(r'Actual:\s+BadRequest\b', message), 'Expected pre-business binding status assertion failure')
            failures.append({'name':key[0], 'testId':key[1], 'message':message, 'stackTrace':stack})
        actual.add(key)
        executions.add(execution)
    require(actual == set(expected), 'Frozen phase roster differs')
    require(len(doc.findall('.//{*}ErrorInfo')) == failed, 'Unexpected summary or extra error evidence')
    diagnostics = set()
    if run_infos:
        for info in run_infos:
            require(set(info.attrib) == {'computerName', 'outcome', 'timestamp'} and info.get('outcome') == 'Error' and bool(info.get('computerName', '').strip()), 'Malformed baseline diagnostic metadata')
            timestamp = info.get('timestamp', '')
            require(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,7}(?:Z|[+-]\d{2}:\d{2})', timestamp), 'Malformed baseline diagnostic timestamp')
            require(datetime.datetime.fromisoformat(timestamp).tzinfo is not None, 'Unzoned baseline diagnostic timestamp')
            text = one(info, './{*}Text', 'Require one baseline diagnostic text')
            require(len(info) == 1 and not len(text) and not text.attrib, 'Unexpected baseline diagnostic content')
            match = re.fullmatch(r'\[xUnit\.net \d{2}:\d{2}:\d{2}\.\d{2}\]     (.+) \[FAIL\]', text.text or '')
            require(match is not None, 'Unexpected runner diagnostic')
            name = match.group(1)
            require(name in {x['name'] for x in failures} and name not in diagnostics, 'Unmapped or duplicate baseline diagnostic')
            diagnostics.add(name)
        require(diagnostics == {x['name'] for x in failures}, 'Baseline diagnostics must bijectively match13 verified failures')
    coverage = list(root.rglob('coverage.cobertura.xml'))
    require(bool(coverage), 'Missing raw coverage')
    digests = {hashlib.sha256(x.read_bytes()).hexdigest() for x in coverage}
    require(len(digests) == 1 and bool(ET.parse(coverage[0]).findall('./packages/package/classes/class/lines/line')), 'Empty or differing coverage copies')
    return {'phase':phase, 'passed':passed, 'failed':failed, 'skipped':0,
            'identities':sorted(actual), 'failures':failures, 'baselineAssertionDiagnostics':sorted(diagnostics),
            'trxSha256':hashlib.sha256(reports[0].read_bytes()).hexdigest(),
            'coverageSha256':next(iter(digests)), 'fullSuiteAcceptance':False,
            'providerDisposalAcceptance':False, 'productionEnrollmentProven':False}


if __name__ == '__main__':
    root = pathlib.Path(sys.argv[1])
    manifest = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8'))
    proof = verify(root, manifest, sys.argv[3], int(sys.argv[4]))
    (root / 'supplier-address-causal-proof.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:proof[k] for k in ('phase','passed','failed','skipped')}))
