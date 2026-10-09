"""Explicit hosted integrity guards. Synthetic controls are not native evidence."""
from pathlib import Path
from collections import Counter
from datetime import datetime
import hashlib,json,os,re,uuid,xml.etree.ElementTree as ET
import yaml

NS={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
PROJECT='Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj'
METHOD='LegacyListUsesFilteredCountAndPreservesExplicitPositiveSize'

class IntegrityError(ValueError):pass

ASSOCIATED_METHOD_COUNTS = {
    'Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementPaginationSourceTests.LegacyListUsesFilteredCountAndPreservesExplicitPositiveSize': 68,
    'Legacy.Maliev.ProcurementService.Tests.Application.ProcurementApplicationServiceTests.OmittedSize_ReachesRepositoryUnchanged': 2,
    'Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementPaginationWireContractTests.ListPage_PreservesRawEnvelopeFlagsNullOmissionAndEmptyStatus': 20,
    'Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementIndependentContactTests.PostAndPutPreserveIndependentContactsThroughFreshReads': 4,
}

BASELINE_FILTER = 'FullyQualifiedName~ProcurementPaginationSourceTests'
CANDIDATE_FILTER = BASELINE_FILTER + '|FullyQualifiedName~OmittedSize_ReachesRepositoryUnchanged|FullyQualifiedName~ProcurementPaginationWireContractTests|FullyQualifiedName~ProcurementIndependentContactTests'
ROSTER_CONTRACT_SHA = 'c84df15498aeb11a53cae5b49c43ef50b232890276dd0851eb79bae00d67408b'
CLASS_RESOURCE_ATTRIBUTION_QUALIFIED = False

def roster_contract():
    path = Path(__file__).resolve().parent / 'compiled-roster-source-contract.json'
    require(sha(path) == ROSTER_CONTRACT_SHA, 'Authenticated/source roster contract drift')
    value = json.loads(path.read_bytes())
    require(value['baseSha'] == '1249989e04040bd1326842ebf2e1f438369cf8c9', 'Original main identity differs')
    original = value['originalMainIdentities']
    require(len(original) == 316 and len({row['displayName'] for row in original}) == 316, 'Original316 unique identities missing')
    require(len(value['associatedDisplayNames']) == len(set(value['associatedDisplayNames'])) == 94, 'Associated94 exact display grammar missing')
    require(len(value['baselineDisplayNames']) == len(set(value['baselineDisplayNames'])) == 16, 'Baseline16 exact display grammar missing')
    return value

def selected_names(complete, testfilter):
    require(testfilter in (BASELINE_FILTER, CANDIDATE_FILTER), 'Unreviewed focused selection')
    terms = [clause.split('~', 1)[1] for clause in testfilter.split('|')]
    selected = [name for name in complete if any(term in name.split('(', 1)[0] for term in terms)]
    require(selected, 'Compiled focused selection empty')
    return selected

def require_class_attribution_qualification(execution_admitted=False):
    require(CLASS_RESOURCE_ATTRIBUTION_QUALIFIED or execution_admitted is True, 'Native qualification/acceptance blocked: three-class exact owned PostgreSQL attribution remains unproved')

def baseline_roster(roster):
    contract = roster_contract()
    expected = [row['displayName'] for row in contract['originalMainIdentities']] + contract['baselineDisplayNames']
    complete = roster.get('allUnfilteredDiscoveredNames')
    require(type(complete) is list and len(complete) == len(set(complete)) == 332 and Counter(complete) == Counter(expected), 'Baseline original316 plus exact16 compiled identities differ')
    require(roster.get('filter') == BASELINE_FILTER and Counter(roster['names']) == Counter(contract['baselineDisplayNames']), 'Baseline exact16 selection differs')

def associated_roster(roster, full):
    require(type(roster) is dict and roster.get('source') == 'compiled-vstest-discovery', 'Independent compiled association required')
    names = roster.get('names')
    complete = roster.get('allUnfilteredDiscoveredNames')
    require(type(names) is list and all(type(name) is str for name in names), 'Associated compiled names missing')
    require(type(complete) is list and len(complete) == 410 and all(type(name) is str for name in complete), 'Complete compiled410 roster required')
    require(len(set(complete)) == 410 and len(set(names)) == len(names), 'Repeated/bare compiled display identities refused')
    contract = roster_contract()
    rename = contract['approvedExistingFactRename']
    original = [row['displayName'] for row in contract['originalMainIdentities']]
    expected_original = [rename['to'] if name == rename['from'] else name for name in original]
    expected_complete = expected_original + contract['associatedDisplayNames']
    require(Counter(complete) == Counter(expected_complete), 'Original316 exact identities or associated94 source display grammar differ')
    require(len(names) == (410 if full else 94), 'Associated selection count differs')
    require(roster.get('filter') is None if full else type(roster.get('filter')) is str and bool(roster['filter']), 'Full association must remain unfiltered')
    selected_counts, complete_counts = Counter(names), Counter(complete)
    require(selected_counts == complete_counts if full else all(selected_counts[name] <= complete_counts[name] for name in names), 'Selected roster not joined to complete discovery')
    require(Counter(names) == Counter(expected_complete if full else contract['associatedDisplayNames']), 'Exact associated source displays missing')
    for method, expected in ASSOCIATED_METHOD_COUNTS.items():
        require(sum(name.split('(', 1)[0] == method for name in complete) == expected, 'Complete associated method roster differs')
        require(sum(name.split('(', 1)[0] == method for name in names) == expected, 'Selected associated method roster differs')
    return {'newCases': 94, 'fullCases': 410, 'methodCounts': dict(ASSOCIATED_METHOD_COUNTS), 'source': 'compiled-vstest-discovery'}

def require(condition,reason):
    if not condition:raise IntegrityError(reason)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def install_spec(text):
    data=yaml.load(text,Loader=yaml.BaseLoader)
    steps=data.get('runs',{}).get('steps',[])
    selected=[step for step in steps if step.get('name')=='Install Gitleaks']
    require(len(selected)==1,'One reviewed Install Gitleaks step required')
    step=selected[0];env=step.get('env')
    require(type(env) is dict and type(env.get('GOTOOLCHAIN')) is str,'Reviewed Go toolchain environment required')
    require(env['GOTOOLCHAIN']=='local' or re.fullmatch(r'go1\.\d+\.\d+(?:\+path)?',env['GOTOOLCHAIN']),'Automatic/floating toolchain refused')
    require(all(re.fullmatch('[A-Z][A-Z0-9_]*',key) and type(value) is str and '${{' not in value and '\n' not in value for key,value in env.items()),'Literal reviewed Go step environment required')
    packages=re.findall(r'^\s*go install (github\.com/zricethezav/gitleaks/v8@(?:[0-9a-f]{40}|v\d+\.\d+\.\d+))\s*(?:#.*)?$',step.get('run',''),re.M)
    require(len(packages)==1,'One exact reviewed Gitleaks package pin required')
    return {'package':packages[0],'env':dict(env),'stepSha256':hashlib.sha256(json.dumps(step,sort_keys=True).encode()).hexdigest()}

def apply_go_spec(environ,spec):
    require(type(spec.get('env')) is dict and 'GOTOOLCHAIN' in spec['env'],'Toolchain cannot be discarded')
    for key,value in spec['env'].items():environ[key]=value
    require(environ.get('GOTOOLCHAIN')==spec['env']['GOTOOLCHAIN'],'Effective Go toolchain differs')
    environ.setdefault('GOFLAGS','-p=1');environ.setdefault('GOMEMLIMIT','512MiB')

def sanitize_runner_env(environ):
    removed=[]
    for key in list(environ):
        upper=key.upper()
        if upper.startswith(('VSTEST','XUNIT','MTP','DOTNET_TEST','MSTEST')) or any(token in upper for token in ('RUNSETTINGS','RUN_SETTINGS','TESTCASEFILTER','TEST_FILTER','TESTFILTER','TESTADAPTERPATH')):
            removed.append(key);del environ[key]
    environ['DOTNET_CLI_UI_LANGUAGE']='en-US';environ['VSLANG']='1033'
    return sorted(removed)

def runner_environment(environ):
    allowed={'PATH','HOME','USER','LOGNAME','SHELL','TMPDIR','TMP','TEMP','LANG','LC_ALL','DOTNET_ROOT','DOTNET_MULTILEVEL_LOOKUP','DOTNET_CLI_HOME','DOTNET_NOLOGO','DOTNET_SKIP_FIRST_TIME_EXPERIENCE','DOTNET_CLI_TELEMETRY_OPTOUT','DOTNET_CLI_UI_LANGUAGE','VSLANG','NUGET_PACKAGES','GITHUB_ACTIONS','GITHUB_WORKSPACE','RUNNER_TEMP','MalievWorkspaceRoot','USE_LOCAL_MALIEV_DEPENDENCIES','MALIEV_TEST_RESOURCE_RUN_ID','MALIEV_TEST_RESOURCE_PHASE','MALIEV_TEST_RESOURCE_RECEIPTS','MALIEV_QUALIFICATION_CASE','MALIEV_QUALIFICATION_CONTROLS','TESTCONTAINERS_RYUK_DISABLED','MSBUILDDISABLENODEREUSE','UseSharedCompilation'}
    result={key:value for key,value in environ.items() if key in allowed}
    result['DOTNET_CLI_UI_LANGUAGE']='en-US';result['VSLANG']='1033';result['NO_COLOR']='1'
    return result

def settings(root):
    path=Path(root)/'owned.runsettings'
    raw=b'<RunSettings><RunConfiguration><MaxCpuCount>1</MaxCpuCount><TestCaseFilter></TestCaseFilter><TreatNoTestsAsError>true</TreatNoTestsAsError></RunConfiguration><xUnit><PreEnumerateTheories>true</PreEnumerateTheories><ParallelizeTestCollections>false</ParallelizeTestCollections><MaxParallelThreads>1</MaxParallelThreads></xUnit></RunSettings>'
    if path.exists():require(path.read_bytes()==raw,'Owned runsettings changed')
    else:path.write_bytes(raw)
    return path

def binary_hashes(cwd):
    folder=Path(cwd)/'Legacy.Maliev.ProcurementService.Tests/bin/Release/net10.0'
    require((folder/'Legacy.Maliev.ProcurementService.Tests.dll').is_file(),'Compiled test assembly missing')
    values={file.relative_to(folder).as_posix():sha(file) for file in sorted(folder.rglob('*')) if file.is_file()}
    require(values,'Empty compiled input inventory');return values

def common_test_args(cwd,runsettings):
    require(Path(runsettings).read_bytes()==settings(Path(runsettings).parent).read_bytes(),'Settings drift')
    return ['dotnet','test',PROJECT,'-c','Release','--no-build','--no-restore','--settings',str(runsettings),'-p:VSTestCLIRunSettings=','-p:VSTestTestAdapterPath=','-p:RunSettingsFilePath='+str(runsettings)]

def observe_roster(driver,label,cwd,testfilter=None):
    removed=sanitize_runner_env(os.environ);runsettings=settings(driver.root)
    folder=Path(cwd)/'Legacy.Maliev.ProcurementService.Tests/bin/Release/net10.0'
    config=folder/'xunit.runner.json'
    raw=json.dumps({'preEnumerateTheories':True,'parallelizeTestCollections':False,'maxParallelThreads':1},sort_keys=True).encode()
    config.write_bytes(raw)
    before=binary_hashes(cwd);argv=common_test_args(cwd,runsettings)+['--list-tests','-p:VSTestTestCaseFilter=']
    _,text=driver.command(label+'-compiled-discovery',argv,cwd,120)
    require(binary_hashes(cwd)==before,'Compiled discovery inputs changed')
    lines=text.splitlines();headers=[i for i,line in enumerate(lines) if line.strip().lower()=='the following tests are available:']
    require(len(headers)==1,'Complete unambiguous compiled discovery header required')
    names=[]
    for line in lines[headers[0]+1:]:
        if not line.strip():continue
        require(line.startswith('    Legacy.Maliev.ProcurementService.Tests.'),'Unexpected/partial/diagnostic discovery output')
        names.append(line.strip())
    require(names,'No compiled test cases discovered')
    complete=names[:]
    if testfilter is not None:
        names=selected_names(complete,testfilter)
    payload={'source':'compiled-vstest-discovery','names':names,'allUnfilteredDiscoveredNames':complete,'binaryHashes':before,'assemblyPath':str((folder/'Legacy.Maliev.ProcurementService.Tests.dll').resolve()),'settingsSha256':sha(runsettings),'discoveryLogSha256':sha(driver.root/(label+'-compiled-discovery.log')),'filter':testfilter,'removedRunnerEnvironmentKeys':removed}
    target=driver.root/(label+'-compiled-roster.json');target.write_text(json.dumps(payload,indent=2))
    driver.receipt.setdefault('compiledRosters',{})[label]={'path':str(target),'sha256':sha(target),'cases':len(names),'filter':testfilter};driver.save()
    return payload

def canonical_uuid(value):
    require(type(value) is str,'Result identity missing')
    try:parsed=uuid.UUID(value)
    except (ValueError,TypeError,AttributeError) as error:raise IntegrityError('Malformed result identity') from error
    require(str(parsed)==value and parsed.int!=0,'Canonical nonzero result identity required')
    return value

def instant(value):
    require(type(value) is str,'Timestamp missing')
    try:parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as error:raise IntegrityError('Malformed timestamp') from error
    require(parsed.tzinfo is not None,'Aware timestamp required');return parsed

def trx(folder,roster,red=False):
    require(type(roster) is dict and roster.get('source')=='compiled-vstest-discovery','Independent compiled roster required; self-count refused')
    require(type(roster.get('names')) is list and roster['names'] and all(type(name) is str and name.startswith('Legacy.Maliev.ProcurementService.Tests.') for name in roster['names']),'Typed compiled display multiset required')
    require(type(roster.get('binaryHashes')) is dict and roster['binaryHashes'] and all(type(key) is str and type(value) is str and re.fullmatch('[0-9a-f]{64}',value) for key,value in roster['binaryHashes'].items()),'Compiled input hashes required')
    files=list(Path(folder).rglob('*.trx'));require(len(files)==1,'One complete TRX required')
    root=ET.parse(files[0]).getroot();require(root.tag=='{'+NS['t']+'}TestRun','TRX namespace/root differs')
    canonical_uuid(root.attrib.get('id'));times=root.find('t:Times',NS);require(times is not None,'Terminal run timing required')
    started=instant(times.attrib.get('start'));finished=instant(times.attrib.get('finish'));require(finished>=started,'Run not completed')
    summaries=root.findall('t:ResultSummary',NS);require(len(summaries)==1,'One terminal summary required');summary=summaries[0]
    require(summary.attrib.get('outcome')==('Failed' if red else 'Completed'),'Terminal TRX outcome differs')
    require(not summary.findall('t:RunInfos/t:RunInfo',NS),'Run-level warnings/errors refused')
    counters=summary.find('t:Counters',NS);require(counters is not None,'Counters missing')
    required={'total','executed','passed','failed','error','timeout','aborted','inconclusive','passedButRunAborted','notRunnable','notExecuted','disconnected','warning','completed','inProgress','pending'}
    require(set(counters.attrib)==required,'Exact typed completion counters required')
    require(all(re.fullmatch(r'[0-9]+',value) for value in counters.attrib.values()),'Invalid counter type')
    counts={key:int(value) for key,value in counters.attrib.items()};expected=len(roster['names'])
    require(counts['total']==counts['executed']==expected and counts['passed']+counts['failed']==expected,'Discovery/result completion count differs')
    require(all(counts[key]==0 for key in required-{'total','executed','passed','failed'}),'Skipped/pending/error run refused')
    results=root.findall('t:Results/t:UnitTestResult',NS);definitions=root.findall('t:TestDefinitions/t:UnitTest',NS);entries=root.findall('t:TestEntries/t:TestEntry',NS)
    require(len(results)==len(definitions)==len(entries)==expected,'Results/definitions/entries incomplete')
    require(Counter(result.attrib.get('testName') for result in results)==Counter(roster['names']),'TRX display multiset differs from independent compiled roster')
    defs={};definition_exec=set()
    for definition in definitions:
        identity=canonical_uuid(definition.attrib.get('id'));require(identity not in defs,'Duplicate definition ID')
        execution=definition.find('t:Execution',NS);method=definition.find('t:TestMethod',NS)
        require(execution is not None and method is not None,'Execution/method definition missing')
        execution_id=canonical_uuid(execution.attrib.get('id'));require(execution_id not in definition_exec,'Repeated definition execution ID');definition_exec.add(execution_id)
        class_name=method.attrib.get('className','').split(',')[0];method_name=method.attrib.get('name','')
        require(class_name.startswith('Legacy.Maliev.ProcurementService.Tests.') and method_name,'Foreign/malformed definition')
        prefix=class_name+'.'+method_name;name=definition.attrib.get('name','')
        require(name==prefix or name.startswith(prefix+'('),'Definition display/method join differs')
        require(definition.attrib.get('storage','').casefold()==roster['assemblyPath'].casefold(),'Definition assembly differs')
        require(method.attrib.get('codeBase','').casefold()==roster['assemblyPath'].casefold(),'Definition codeBase differs')
        defs[identity]=(name,execution_id)
    pairs=set()
    for entry in entries:
        pair=(canonical_uuid(entry.attrib.get('testId')),canonical_uuid(entry.attrib.get('executionId')))
        require(pair not in pairs,'Repeated test entry');pairs.add(pair)
    seen_test=set();seen_execution=set();failed=[];passed=0
    for result in results:
        identity=canonical_uuid(result.attrib.get('testId'));execution=canonical_uuid(result.attrib.get('executionId'))
        require(identity not in seen_test and execution not in seen_execution,'Repeated test/execution identity');seen_test.add(identity);seen_execution.add(execution)
        require(identity in defs and defs[identity]==(result.attrib['testName'],execution) and (identity,execution) in pairs,'Result/definition/entry join differs')
        start=instant(result.attrib.get('startTime'));end=instant(result.attrib.get('endTime'));require(start>=started and end>=start and end<=finished,'Result timing incomplete/outside run')
        outcome=result.attrib.get('outcome');require(outcome in ('Passed','Failed'),'Skipped/incomplete result refused')
        if outcome=='Passed':passed+=1;continue
        message=result.findtext('t:Output/t:ErrorInfo/t:Message','',NS);stack=result.findtext('t:Output/t:ErrorInfo/t:StackTrace','',NS)
        require(red and 'Assert.Equal() Failure' in message and METHOD in stack and METHOD in result.attrib['testName'],'RED failure is not the exact behavioral assertion')
        require(re.search(r'\bsize:\s*(?:null|251|999)(?=\s*[,)]|$)',result.attrib['testName']) is not None,'RED size not in reviewed omission/positive baseline')
        require(not any(word in message for word in ('Exception','Npgsql','Docker','Unauthorized','Forbidden','InternalServerError')),'Infrastructure failure cannot qualify RED')
        failed.append(result.attrib['testName'])
    require(set(defs)==seen_test and passed==counts['passed'] and len(failed)==counts['failed'],'Completed result/counter mismatch')
    require(bool(failed)==red,'Expected behavioral RED/green differs')
    return {'actualCases':expected,'passed':passed,'failed':len(failed),'failures':failed,'trxSha256':sha(files[0]),'independentRosterMatched':True,'uniqueIdentitiesVerified':True,'terminalCountersVerified':True}
