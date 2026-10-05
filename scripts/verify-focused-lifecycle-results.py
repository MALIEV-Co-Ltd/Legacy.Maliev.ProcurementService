"""Require actual execution of every declared address and child lifecycle case."""
import collections
import hashlib
import json
import pathlib
import sys
import xml.etree.ElementTree as ET

root = pathlib.Path(sys.argv[1])
manifest = json.loads(pathlib.Path('docs/procurement-focused-lifecycle-contract.json').read_text(encoding='utf-8'))
reports = list(root.rglob('*.trx'))
if len(reports) != 1:
    raise SystemExit('Expected one focused TRX; a failed build is not executed acceptance.')
document = ET.parse(reports[0])
counters = document.find('.//{*}Counters')
results = document.findall('.//{*}UnitTestResult')
expected = manifest['expectedCases']
actual = collections.Counter(result.get('testName', '').split('(')[0] for result in results)
if counters is None or any(int(counters.get(key, '-1')) != expected for key in ('total', 'executed', 'passed')):
    raise SystemExit('Focused cases must all execute and pass.')
if int(counters.get('failed', '-1')) != 0 or int(counters.get('notExecuted', '-1')) != 0:
    raise SystemExit('Failed or skipped focused cases cannot establish acceptance.')
if actual != manifest['expectedMethods'] or any(result.get('outcome') != 'Passed' for result in results):
    raise SystemExit('Actual focused method/cardinality/outcome differs from the declared contract.')
coverage = list(root.rglob('coverage.cobertura.xml'))
digests = {hashlib.sha256(path.read_bytes()).hexdigest() for path in coverage}
if len(digests) != 1 or not ET.parse(coverage[0]).findall('./packages/package/classes/class/lines/line'):
    raise SystemExit('Expected executable unfiltered focused raw evidence.')
proof = {'executed': expected, 'passed': expected, 'failed': 0, 'skipped': 0,
         'actualMethods': dict(actual), 'rawSha256': next(iter(digests)), 'exclusions': [],
         'fullServiceCoverageAcceptance': False, 'employeeLiveIamAcceptance': False}
(root / 'focused-lifecycle-proof.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
print(json.dumps(proof))
