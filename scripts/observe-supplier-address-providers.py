"""Observe a bounded filtered test process; never delete an uncertain resource."""
import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from supplier_address_owned_processes import OwnedSession, process_identity


def docker(*args, timeout=10):
    return subprocess.check_output(['docker', *args], timeout=timeout, text=True)


def ids():
    return set(docker('ps', '-a', '--no-trunc', '--format', '{{.ID}}').split())


def volumes():
    return set(docker('volume', 'ls', '--format', '{{.Name}}').split())


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise ValueError(message)


def observe(workspace, output, phase):
    output.mkdir(parents=True, exist_ok=False)
    created = {}
    observed_at = utc()
    started = time.monotonic()
    process = None
    session = None
    errors = []
    exit_code = None
    cleanup = None
    environment = dict(os.environ, GITHUB_ACTIONS='false', VSTestResultsDirectory=str(output.resolve()))
    command = ['dotnet', 'test', 'Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj',
               '--configuration', 'Release', '--no-build', '--no-restore', '--disable-build-servers', '-p:UseLocalMalievDependencies=true',
               '--filter', 'FullyQualifiedName~ProcurementSupplierAddressScalarStringTests',
               '--logger', 'trx', '--collect', 'XPlat Code Coverage']
    receipt = {'phase':phase, 'startedAtUtc':observed_at, 'timeoutSeconds':300,
               'command':command, 'workspace':str(workspace.resolve()), 'resources':[],
               'owningRun':os.environ.get('GITHUB_RUN_ID'), 'owningAttempt':os.environ.get('GITHUB_RUN_ATTEMPT'),
               'purpose':'Supplier address33 isolated phase', 'persistentData':False,
               'hostedJobLeaseMinutes':30, 'normalFixtureDisposalProven':False}
    try:
        require(phase in ('baseline', 'candidate'), 'Unknown phase')
        initial_ids, initial_volumes = ids(), volumes()
        try:
            with (output/'test-console.log').open('w', encoding='utf-8') as log:
                process = subprocess.Popen(command, cwd=workspace, env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                receipt['processIdentity'] = process_identity(process.pid)
                session = OwnedSession(process)
                session.capture()
                while process.poll() is None:
                    session.capture()
                    require(time.monotonic()-started < 300, 'Filtered test process timed out')
                    live_ids = ids()
                    pending_starts = {key for key, value in created.items() if value['startedAt'].startswith('0001-')}
                    for container_id in (live_ids-initial_ids-created.keys()) | (pending_starts & live_ids):
                        try:
                            metadata = json.loads(docker('inspect', container_id))[0]
                        except subprocess.CalledProcessError:
                            continue
                        image = metadata['Config']['Image']
                        if image != 'postgres:18.1-bookworm' and not image.startswith('testcontainers/ryuk:'):
                            continue
                        labels = {k:v for k,v in (metadata['Config'].get('Labels') or {}).items() if k.startswith('org.testcontainers')}
                        created[container_id] = {'id':metadata['Id'], 'created':metadata['Created'],
                            'startedAt':metadata['State']['StartedAt'], 'image':image, 'imageId':metadata['Image'],
                            'labels':labels, 'ports':metadata['NetworkSettings']['Ports'],
                            'mounts':[{'type':m['Type'], 'name':m.get('Name'), 'destination':m['Destination'],
                                       'preexisting':m.get('Name') in initial_volumes} for m in metadata['Mounts']]}
                    time.sleep(0.25)
                exit_code = process.wait(timeout=10)
        finally:
            execution_failed = sys.exc_info()[0] is not None
            try:
                if session is not None:
                    cleanup = session.cleanup(failed=execution_failed)
                    if not cleanup['verified'] or cleanup['forcedCleanup'] or not cleanup['handlesClosed']:
                        errors.append('Owned session needed cleanup or lacks terminal proof; phase is not accepted')
                elif process is not None:
                    errors.append('Session custody unavailable; child state is unknown and phase is refused')
                    try:
                        if process.poll() is None:
                            process.terminate()
                    except BaseException as error:
                        errors.append('launcher terminate: ' + type(error).__name__ + ': ' + str(error))
                    try:
                        process.wait(timeout=3)
                    except BaseException as error:
                        errors.append('launcher wait: ' + type(error).__name__ + ': ' + str(error))
                        try:
                            if process.poll() is None:
                                process.kill()
                            process.wait(timeout=3)
                        except BaseException as kill_error:
                            errors.append('launcher final cleanup: ' + type(kill_error).__name__ + ': ' + str(kill_error))
            except BaseException as error:
                errors.append('cleanup: ' + type(error).__name__ + ': ' + str(error))
            receipt['processSessionCleanup'] = cleanup
            receipt['processEndedAtUtc'] = utc()
            receipt['endedAtUtc'] = receipt['processEndedAtUtc']
        require(not errors, 'Observation or process cleanup failed; raw receipt retained')
        logs = (output/'test-console.log').read_text(encoding='utf-8')
        reports = list(output.rglob('*.trx'))
        require(len(reports) == 1, 'Require actual filtered TRX for container ownership')
        doc = ET.parse(reports[0])
        logs += '\n'.join(x.text or '' for x in doc.findall('.//{*}StdOut'))
        postgres = [r for r in created.values() if r['image']=='postgres:18.1-bookworm']
        require(len(postgres)==2, 'Exactly two live PostgreSQL metadata records required')
        session_ids = set()
        for resource in postgres:
            short = resource['id'][:12]
            require(re.search(r'Docker container '+short+r' created', logs) and
                    re.search(r'Start Docker container '+short, logs) and
                    re.search(r'Delete Docker container '+short, logs), 'Provider IDs not bound to actual test process creation/start/disposal logs')
            session = resource['labels'].get('org.testcontainers.session-id')
            require(bool(session), 'Missing actual Testcontainers session ownership')
            session_ids.add(session)
            require(resource['startedAt'] and not resource['startedAt'].startswith('0001-'), 'Provider start time not observed')
            require(all(m['type']=='volume' and m['name'] and not m['preexisting'] for m in resource['mounts']), 'Unexpected or preexisting persistent mount')
        require(len(session_ids)==1, 'Providers belong to different sessions')
        current_ids, current_volumes = ids(), volumes()
        owned = [r for r in created.values() if r['labels'].get('org.testcontainers.session-id') in session_ids]
        require(all(r['id'] not in current_ids for r in owned), 'Owned helper/container remains after fixture disposal')
        require(all(m['name'] not in current_volumes for r in postgres for m in r['mounts']), 'Provider volume remains after fixture disposal')
        events_raw = docker('events','--since',observed_at,'--until',receipt['endedAtUtc'],'--format','{{json .}}')
        events = [json.loads(line) for line in events_raw.splitlines() if line.strip()]
        bound_events = []
        for resource in postgres:
            matches = [e for e in events if e.get('Type')=='container' and e.get('Actor',{}).get('ID')==resource['id']]
            actions = [e.get('Action') for e in matches]
            require('start' in actions and 'die' in actions and 'destroy' in actions and actions.index('start')<actions.index('die')<actions.index('destroy'), 'Missing ordered provider lifecycle events')
            bound_events.extend({'id':resource['id'],'action':e['Action'],'timeNano':e.get('timeNano')} for e in matches if e.get('Action') in ('create','start','die','destroy'))
        receipt.update(normalFixtureDisposalProven=True, resourcesAbsent=True, ownedSessionIds=sorted(session_ids), events=bound_events,
                       rawTrxSha256=hashlib.sha256(reports[0].read_bytes()).hexdigest())
        return exit_code
    except BaseException as error:
        receipt['primaryFailure'] = {'category':type(error).__name__, 'message':str(error)}
        errors.append(type(error).__name__ + ': ' + str(error))
        raise
    finally:
        active_exception = sys.exc_info()[0] is not None
        try:
            receipt['processExited'] = process is not None and process.poll() is not None
        except BaseException as error:
            receipt['processExited'] = False
            receipt.setdefault('primaryFailure', {'category':type(error).__name__, 'message':str(error)})
            errors.append('exit observation: ' + type(error).__name__ + ': ' + str(error))
        receipt['processSessionCleanup'] = cleanup
        receipt['exitCode'] = exit_code
        receipt['endedAtUtc'] = utc()
        receipt['resources'] = list(created.values())
        receipt['errors'] = errors
        receipt['uncertainResourcesPreserved'] = not receipt['normalFixtureDisposalProven'] or bool(errors)
        if errors:
            receipt['normalFixtureDisposalProven'] = False
        (output/'provider-observation.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
        if errors and not active_exception:
            raise ValueError('Final process observation failed; raw receipt retained')


if __name__ == '__main__':
    code=observe(pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]),sys.argv[3])
    (pathlib.Path(sys.argv[2])/'test-exit-code.txt').write_text(str(code)+'\n',encoding='utf-8')
