"""Linux hosted-only baseline RED and candidate focused validation; no publication."""
from pathlib import Path
import argparse, hashlib, json, os, re, selectors, shutil, signal, subprocess, sys, time, uuid, zipfile
import xml.etree.ElementTree as ET
from procurement_pagination_hosted_guards import IntegrityError, require, install_spec, apply_go_spec, sanitize_runner_env, runner_environment, settings, binary_hashes, common_test_args, observe_roster, trx, associated_roster, baseline_roster, BASELINE_FILTER, CANDIDATE_FILTER, require_class_attribution_qualification
from procurement_fixture_attribution import observe as observe_fixture, prove as prove_fixture, install as install_fixture
OWNER = '01a1009c-aa47-72d2-9914-3a0784a67c0e'
BASE = '1249989e04040bd1326842ebf2e1f438369cf8c9'
PACKET_SHA = 'd8748cf62c5ee7bd88b6cadbd949cb6056d4662d83e9153493328d0a95f06658'
MANIFEST_SHA = 'af76f4d18ecabe559d9e0a47077febbfaf209daa4f72a772733f5a22412726a7'
PROJECT = 'Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj'
FILTER = BASELINE_FILTER
NS = {'t': 'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
LIMIT = 32 * 1024 * 1024

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class Driver:

    def __init__(self, root, run):
        self.root = root
        self.run = run
        self.receipt = {'owner': OWNER, 'run': run, 'processes': [], 'postgres': {}, 'phases': {}}
        self.bytes = 0

    def save(self):
        (self.root / 'receipt.json').write_text(json.dumps(self.receipt, indent=2))

    @staticmethod
    def birth(pid):
        raw = Path(f'/proc/{pid}/stat').read_text()
        return raw[raw.rfind(')') + 2:].split()[19]

    def command(self, name, argv, cwd, timeout, allow_failure=False, monitor=False):
        if self.receipt.get('hostedExecutionBinding'):
            from procurement_hosted_binding import remaining
            require(remaining(self.receipt['hostedExecutionBinding']) >= timeout + 15, 'Original allocation cannot cover command and unchanged cleanup cap')
        if argv[0] in ('dotnet', 'go'):
            mem = re.search('MemAvailable:\\s+(\\d+)', Path('/proc/meminfo').read_text())
            if not mem or int(mem.group(1)) < 4194304:
                raise RuntimeError('Fresh 4GiB admission floor unavailable')
        start = time.monotonic()
        log = self.root / (name + '.log')
        from datetime import datetime, timezone, timedelta
        proc = sel = None
        row = {'name': name, 'timeoutSeconds': timeout, 'started': False, 'exited': False, 'handleClosed': False, 'stdoutClosed': False, 'selectorClosed': False, 'cleanupFailures': []}
        self.receipt['processes'].append(row)
        row['commandAbsoluteDeadlineMonotonic'] = start + timeout + 15
        row['outerCustodyExpiresUtc'] = (datetime.now(timezone.utc) + timedelta(seconds=timeout + 15)).isoformat()
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=runner_environment(os.environ) if argv[0] == 'dotnet' else os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            row.update(pid=proc.pid, started=True, birth=None, executable=None)
            row['birth'] = self.birth(proc.pid)
            row['executable'] = str(Path(f'/proc/{proc.pid}/exe').resolve(strict=True))
            self.save()
            sel = selectors.DefaultSelector()
            sel.register(proc.stdout, selectors.EVENT_READ)
            next_probe = 0
            with log.open('xb') as f:
                while sel.get_map():
                    if time.monotonic() - start > timeout:
                        raise TimeoutError(name)
                    if monitor and time.monotonic() > next_probe:
                        self.probe_postgres()
                        next_probe = time.monotonic() + 2
                    for key, _ in sel.select(0.2):
                        raw = os.read(key.fileobj.fileno(), 65536)
                        if not raw:
                            sel.unregister(key.fileobj)
                            continue
                        self.bytes += len(raw)
                        if self.bytes > LIMIT:
                            raise RuntimeError('Aggregate output quota')
                        f.write(raw)
                code = proc.wait(timeout=5)
                row['exitCode'] = code
                if code != 0 and (not allow_failure):
                    raise RuntimeError(name + ' failed; see retained log')
                return (code, log.read_text(errors='replace'))
        finally:
            primary = sys.exception()
            try: self._settle_command(proc, row, sel, primary)
            except BaseException as cleanup_error:
                if primary is None: raise
                try: primary.add_note('Secondary command cleanup failure: ' + type(cleanup_error).__name__)
                except BaseException: pass

    def _settle_command(self, proc, row, sel, primary):
        # Independently settle exact task custody; never replace an active primary failure.
        failures = []
        def failed(boundary, error):
            failures.append({'boundary': boundary, 'type': type(error).__name__})
        members = []
        enumerated = proc is None
        if proc is not None:
            deadline = row.setdefault('cleanupAbsoluteDeadlineMonotonic', min(row['commandAbsoluteDeadlineMonotonic'], time.monotonic() + 10.3))
            row['outerCustodyExpired'] = time.monotonic() >= row['commandAbsoluteDeadlineMonotonic']
            try:
                leader_reused = False
                if row.get('birth') is not None:
                    try: leader_reused = self.birth(proc.pid) != row['birth']
                    except (FileNotFoundError, ProcessLookupError): pass
                if leader_reused:
                    raise RuntimeError('Leader PID identity changed; session ownership unproved')
                if row.get('birth') is None and proc.poll() is not None:
                    raise RuntimeError('Partial-start exited child has no proved session birth')
                for item in Path('/proc').iterdir():
                    if not item.name.isdigit(): continue
                    try:
                        stat = (item / 'stat').read_text()
                        fields = stat[stat.rfind(')') + 2:].split()
                        if int(fields[3]) == proc.pid:
                            members.append((int(item.name), fields[19]))
                    except (FileNotFoundError, ProcessLookupError): pass
                enumerated = True
            except BaseException as error: failed('session-inventory', error)
            # A retained Popen child is also settled if metadata/selector startup failed.
            for sig in (signal.SIGTERM, signal.SIGKILL):
                for pid, birth in members:
                    try:
                        if self.birth(pid) == birth: os.kill(pid, sig)
                    except (FileNotFoundError, ProcessLookupError): pass
                    except BaseException as error: failed('exact-session-signal', error)
                try:
                    if proc.poll() is None:
                        if row.get('birth') is None or self.birth(proc.pid) == row['birth']:
                            (proc.terminate if sig == signal.SIGTERM else proc.kill)()
                except (FileNotFoundError, ProcessLookupError): pass
                except BaseException as error: failed('retained-child-signal', error)
                if sig == signal.SIGTERM:
                    try:
                        grace_remaining = deadline-time.monotonic()
                        if grace_remaining > 0: time.sleep(min(0.3, grace_remaining))
                    except BaseException as error: failed('grace-wait', error)
            row['cleanupWaitBudgetSeconds'] = 10
            for attempt in range(2):
                try:
                    remaining_wait = deadline-time.monotonic()
                    if remaining_wait <= 0: break
                    proc.wait(timeout=min(5, remaining_wait))
                    break
                except BaseException as error: failed('retained-child-wait', error)
            try:
                row['exited'] = proc.poll() is not None
            except BaseException as error: failed('exit-observation', error)
        else:
            row['exited'] = True
        remaining = []
        for pid, birth in members:
            try:
                stat = Path(f'/proc/{pid}/stat').read_text()
                fields = stat[stat.rfind(')') + 2:].split()
                if fields[19] == birth and fields[0] != 'Z': remaining.append(pid)
            except (FileNotFoundError, ProcessLookupError): pass
            except BaseException as error:
                enumerated = False
                failed('exact-member-exit', error)
        if proc is not None and enumerated:
            try:
                known = set(members)
                for item in Path('/proc').iterdir():
                    if not item.name.isdigit(): continue
                    try:
                        stat = (item / 'stat').read_text()
                        fields = stat[stat.rfind(')') + 2:].split()
                        if int(fields[3]) == proc.pid and fields[0] != 'Z' and (int(item.name), fields[19]) not in known:
                            enumerated = False
                            failed('new-session-writer', RuntimeError('Unobserved session member'))
                    except (FileNotFoundError, ProcessLookupError): pass
            except BaseException as error:
                enumerated = False
                failed('terminal-session-inventory', error)
        row['privateSessionMembers'] = [{'pid': pid, 'birth': birth} for pid, birth in members]
        row['liveOwnedSessionMembersRemaining'] = remaining
        # Selector closure does not close the pipe. Pipe closure requires all writers settled.
        if sel is not None:
            try: sel.close(); row['selectorClosed'] = True
            except BaseException as error: failed('selector-close', error)
        else: row['selectorClosed'] = True
        safe_pipe = row['exited'] and enumerated and not remaining
        if proc is None: row['stdoutClosed'] = True
        elif safe_pipe:
            try: proc.stdout.close(); row['stdoutClosed'] = True
            except BaseException as error: failed('stdout-close', error)
        row['handleClosed'] = row['stdoutClosed'] and row['selectorClosed']
        row['ownedIdentityAbsent'] = proc is None
        if proc is not None:
            try:
                row['ownedIdentityAbsent'] = not Path(f'/proc/{proc.pid}').exists() or (row.get('birth') is not None and self.birth(proc.pid) != row['birth'])
            except (FileNotFoundError, ProcessLookupError): row['ownedIdentityAbsent'] = True
            except BaseException as error: failed('identity-absence', error)
        row['cleanupFailures'].extend(failures)
        custody = getattr(self, '_pending_commands', [])
        custody = [entry for entry in custody if entry[1] is not row]
        if not row['handleClosed'] or not row['exited'] or not enumerated or remaining:
            custody.append((proc, row, None if row['selectorClosed'] else sel))
            row['outerCustodyRequired'] = True
            row['outerCustodyRun'] = self.run
            row['originalCommandTimeoutSeconds'] = row['timeoutSeconds']
            row['outerCustodyReason'] = 'Exact exit/writer or handle settlement unproved; retained objects, no live-writer pipe closure.'
        else: row['outerCustodyRequired'] = False
        self._pending_commands = custody
        try: self.save()
        except BaseException as error:
            failed('receipt-save', error)
            row['cleanupFailures'].append(failures[-1])
        if failures or row['outerCustodyRequired']:
            if primary is not None:
                try: primary.add_note('Owned command cleanup has secondary failure or retained outer custody; inspect process receipt.')
                except BaseException: pass
            else: raise RuntimeError('Exact owned command cleanup incomplete; inspect retained receipt')

    def quick(self, argv, timeout=8):
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        row = {'name': 'bounded ownership/probe CLI', 'pid': proc.pid, 'birth': self.birth(proc.pid), 'executable': str(Path(f'/proc/{proc.pid}/exe').resolve()), 'timeoutSeconds': timeout, 'exited': False, 'handleClosed': False}
        self.receipt['processes'].append(row)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            if len(stdout) + len(stderr) > 2 * 1024 * 1024:
                raise RuntimeError('Metadata quota')
            return (proc.returncode, stdout)
        finally:
            if proc.poll() is None:
                if self.birth(proc.pid) == row['birth']:
                    proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    if self.birth(proc.pid) == row['birth']:
                        proc.kill()
                    proc.wait(timeout=3)
            row['exited'] = True
            proc.stdout.close()
            proc.stderr.close()
            row['handleClosed'] = True
            row['ownedIdentityAbsent'] = not Path(f'/proc/{proc.pid}').exists()
            self.save()

    def docker(self, *args):
        code, raw = self.quick(['docker', *args])
        if code:
            raise RuntimeError('Docker ownership/readback command failed')
        return raw.decode()

    def owned_containers(self):
        return self.docker('ps', '-aq', '--no-trunc', '--filter', 'label=maliev.codex.owner=commerce-procurement-qualification-20261007', '--filter', 'label=maliev.codex.parent-run=' + self.run).split()

    def inspect(self, cid):
        value = json.loads(self.docker('inspect', cid))[0]
        labels = value['Config']['Labels']
        host = value['HostConfig']
        require(value['Id'] == cid and labels['maliev.codex.owner'] == 'commerce-procurement-qualification-20261007', "Integrity guard: value['Id'] == cid and labels['maliev.codex.owner'] == 'commerce-procurement-qualification-20261007'")
        require(labels['maliev.codex.parent-run'] == self.run and labels['maliev.codex.persistent-data'] == 'false', "Integrity guard: labels['maliev.codex.parent-run'] == self.run and labels['maliev.codex.persistent-data'] == 'false'")
        require(host['Memory'] == 1073741824 and host['MemorySwap'] == 1073741824 and (host['NanoCpus'] == 750000000), "Integrity guard: host['Memory'] == 1073741824 and host['MemorySwap'] == 1073741824 and (host['NanoCpus'] == 750000000)")
        require(host['Tmpfs'].get('/var/lib/postgresql') == 'rw,size=512m', "Integrity guard: host['Tmpfs'].get('/var/lib/postgresql') == 'rw,size=512m'")
        require(all((port['HostIp'] == '127.0.0.1' for ports in value['NetworkSettings']['Ports'].values() if ports for port in ports)), "Integrity guard: all((port['HostIp'] == '127.0.0.1' for ports in value['NetworkSettings']['Ports'].values() if ports for port in ports))")
        require(not any((mount['Type'] in ('bind', 'volume') for mount in value.get('Mounts', []))), "Integrity guard: not any((mount['Type'] in ('bind', 'volume') for mount in value.get('Mounts', [])))")
        row = {'id': cid, 'createdUtc': value['Created'], 'image': value['Config']['Image'], 'labels': labels, 'memory': host['Memory'], 'nanoCpus': host['NanoCpus'], 'persistentData': False}
        return (value, row)

    def probe_postgres(self):
        for cid in self.owned_containers():
            value, row = self.inspect(cid)
            old = self.receipt['postgres'].get(cid, {})
            if old.get('serverVersionNum'):
                continue
            if value['State']['Running']:
                code, stdout = self.quick(['docker', 'exec', cid, 'psql', '-U', 'postgres', '-d', 'postgres', '-Atc', 'SHOW server_version_num'], timeout=3)
                raw = stdout.decode().strip()
                if code == 0 and raw.isdigit():
                    require(180000 <= int(raw) < 190000, 'Integrity guard: 180000 <= int(raw) < 190000')
                    row['serverVersionNum'] = int(raw)
            self.receipt['postgres'][cid] = row
        if hasattr(self, 'fixture_phase'):
            observe_fixture(self, self.fixture_phase, self.fixture_directory)
        self.save()

    def begin_fixture_phase(self, phase):
        from datetime import datetime, timezone
        self.fixture_phase = phase
        self.fixture_directory = self.root / (phase + '-fixture-receipts')
        self.fixture_directory.mkdir()
        self.receipt.setdefault('fixturePhaseStarts', {})[phase] = datetime.now(timezone.utc).isoformat()
        self.save()
        os.environ['MALIEV_TEST_RESOURCE_PHASE'] = phase
        os.environ['MALIEV_TEST_RESOURCE_RECEIPTS'] = str(self.fixture_directory.resolve())

    def finish_fixture_phase(self):
        observe_fixture(self, self.fixture_phase, self.fixture_directory)
        self.cleanup()
        proof = prove_fixture(self, self.fixture_phase, self.fixture_directory)
        self.receipt.setdefault('fixtureQualification', {})[self.fixture_phase] = proof
        self.save()

    def cleanup(self):
        failures = []
        for cid in self.owned_containers():
            try:
                self.inspect(cid)
                self.docker('stop', '--time', '5', cid)
                self.inspect(cid)
                self.docker('rm', cid)
            except Exception as exc:
                failures.append(type(exc).__name__)
        absent = not self.owned_containers()
        self.receipt['cleanup'] = {'ownedContainersAbsent': absent, 'failures': failures}
        self.save()
        if failures or not absent:
            raise RuntimeError('Owned container cleanup incomplete')

    def finish(self):
        pending = sys.exception()
        custody_error = None
        for proc, row, sel in list(getattr(self, '_pending_commands', [])):
            try: self._settle_command(proc, row, sel, pending)
            except BaseException as error:
                self.receipt['commandCustodyFailure'] = type(error).__name__
                if custody_error is None: custody_error = error
        try:
            self.cleanup()
        except BaseException as exc:
            self.receipt['cleanupFailure'] = type(exc).__name__
            self.save()
            if pending is None:
                raise
        if pending is None and custody_error is not None:
            raise custody_error

def prepare(args, driver):
    from procurement_consumer_association import verify_context
    driver.receipt['originalConsumerSourceAssociation'] = verify_context(args.base, os.environ['MalievWorkspaceRoot'])
    require(args.shared_sha == driver.receipt['originalConsumerSourceAssociation']['qualifiedSharedSourceCommit'], 'Original published shared source revision differs')
    driver.save()
    require(os.name == 'posix' and os.environ.get('GITHUB_ACTIONS') == 'true', "Integrity guard: os.name == 'posix' and os.environ.get('GITHUB_ACTIONS') == 'true'")
    require(re.fullmatch('[0-9a-f]{40}', args.shared_sha), "Integrity guard: re.fullmatch('[0-9a-f]{40}', args.shared_sha)")
    require(args.shared_sha != 'e3a6093324a24968876782153286f52db8b29fd8', "Integrity guard: args.shared_sha != 'e3a6093324a24968876782153286f52db8b29fd8'")
    require(digest(args.packet) == PACKET_SHA, 'Integrity guard: digest(args.packet) == PACKET_SHA')
    packet = driver.root / 'packet'
    packet.mkdir()
    with zipfile.ZipFile(args.packet) as z:
        require(len(z.namelist()) == 8 and len(set(z.namelist())) == 8 and all((not name.startswith('/') and '..' not in Path(name).parts for name in z.namelist())), 'Exact eight unique safe packet entries required')
        z.extractall(packet)
    require(digest(packet / 'manifest.json') == MANIFEST_SHA, "Integrity guard: digest(packet / 'manifest.json') == MANIFEST_SHA")
    manifest = json.loads((packet / 'manifest.json').read_bytes())
    require(manifest['baseSha'] == BASE, "Integrity guard: manifest['baseSha'] == BASE")
    require(set(z.namelist()) == {'manifest.json'} | {'candidate/' + row['path'] for row in manifest['changes']}, 'Packet entries differ from reviewed seven-file source')
    for row in manifest['changes']:
        require(digest(packet / 'candidate' / row['path']) == row['postimageSha256'], "Integrity guard: digest(packet / 'candidate' / row['path']) == row['postimageSha256']")
    code, head = driver.command('base-identity', ['git', 'rev-parse', 'HEAD'], args.base, 10)
    require(head.strip() == BASE, 'Integrity guard: head.strip() == BASE')
    for row in manifest['sourceJoins']:
        require(digest(Path(args.base) / row['path']) == row['sha256'], 'Current-main source/instruction join differs')
    for row in manifest['changes']:
        path = Path(args.base) / row['path']
        require((not path.exists()) if row['preimageSha256'] is None else digest(path) == row['preimageSha256'], 'Business preimage differs')
    for phase in ('baseline', 'candidate'):
        dest = driver.root / phase
        shutil.copytree(args.base, dest, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'))
        for row in manifest['changes']:
            path = row['path']
            if phase == 'baseline' and (not path.endswith('ProcurementPaginationSourceTests.cs')):
                continue
            target = dest / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((packet / 'candidate' / path).read_bytes())
        tests = dest / 'Legacy.Maliev.ProcurementService.Tests'
        helper = Path(args.helper)
        assembly = Path(args.assembly)
        require(digest(helper) == args.helper_sha and digest(assembly) == args.assembly_sha, 'Integrity guard: digest(helper) == args.helper_sha and digest(assembly) == args.assembly_sha')
        shutil.copyfile(helper, tests / 'OwnedProcurementTestContainers.cs')
        shutil.copyfile(assembly, tests / 'ProcurementResourceAssembly.cs')
        replacements = 0
        for file in tests.rglob('*.cs'):
            if file.name == 'OwnedProcurementTestContainers.cs':
                continue
            text = file.read_text(encoding='utf-8-sig')
            changed = text.replace('new PostgreSqlBuilder(', 'OwnedProcurementTestContainers.Postgres(')
            replacements += text.count('new PostgreSqlBuilder(')
            if changed != text:
                file.write_text(changed, encoding='utf-8')
        require(replacements == 9, 'Integrity guard: replacements == 9')
        install_fixture(tests, phase)
        if phase == 'baseline':
            regression = dest / 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementPaginationSourceTests.cs'
            text = regression.read_text()
            old = 'foreach (var value in cases)'
            require(text.count(old) == 1, 'Integrity guard: text.count(old) == 1')
            regression.write_text(text.replace(old, 'foreach (var value in cases.Where(value => value.Index is null && ((value.Size is null && (value.Search == "match" || value.Search is null)) || ((value.Size == 251 || value.Size == 999) && value.Search == "match"))))'))
            driver.receipt['baselineSelection'] = {'cases': 16, 'meaning': 'Omitted filtered503/unfiltered510 and explicit251/999 first page; two routes and both ID sort directions. All68 candidate HTTP cases unchanged.', 'selectedSourceSha256': digest(regression)}
        driver.command(phase + '-git-init', ['git', 'init'], dest, 10)
        driver.command(phase + '-git-index', ['git', 'add', '.'], dest, 20)
    driver.receipt['resourceOverlay'] = {'helperSha256': args.helper_sha, 'assemblySha256': args.assembly_sha, 'builderSites': 9, 'businessManifestSha256': MANIFEST_SHA}
    driver.save()

def main():
    require(os.name == 'posix' and os.environ.get('GITHUB_ACTIONS') == 'true', 'Hosted Linux entry required')
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['focused', 'full', 'injections', 'cleanup'], required=True)
    for name in ('root', 'base', 'packet', 'shared-sha', 'shared-checkout', 'helper', 'helper-sha', 'assembly', 'assembly-sha'):
        parser.add_argument('--' + name, required=name == 'root')
    args = parser.parse_args()
    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)
    run = os.environ.get('MALIEV_TEST_RESOURCE_RUN_ID')
    require(run and uuid.UUID(run), 'Integrity guard: run and uuid.UUID(run)')
    driver = Driver(root, run)
    if (root / 'receipt.json').exists():
        driver.receipt = json.loads((root / 'receipt.json').read_bytes())
    if args.phase == 'cleanup':
        driver.cleanup()
        return
    # A fresh exact original hosted allocation permits collecting qualification
    # evidence; it does not qualify attribution or grant native acceptance.
    from procurement_hosted_binding import admit
    binding = admit(os.environ.get('MALIEV_PROCUREMENT_ALLOCATION_FILE', ''), os.environ.get('MALIEV_PROCUREMENT_ALLOCATION_SHA'))
    prior = driver.receipt.get('hostedExecutionBinding')
    require(prior is None or all(prior[key] == binding[key] for key in ('allocationId', 'expiresUtc', 'transportCommit', 'runId', 'runAttempt')), 'Original hosted allocation changed between phases')
    driver.receipt['hostedExecutionBinding'] = binding
    driver.save()
    require_class_attribution_qualification(execution_admitted=binding['qualificationExecutionAllowed'])
    if args.phase == 'injections':
        require(driver.receipt.get('owner') == OWNER and driver.receipt.get('run') == run, 'Original owned run receipt required')
        suite = driver.receipt.get('fullSuite', {})
        require(suite.get('actualCases') == 410 and suite.get('passed') == 410 and suite.get('failed') == 0, 'Original actual410 full proof required')
        require(driver.receipt.get('effectiveGoVersion', '').startswith('go version go1.26.9 '), 'Existing qualified actual Go1.26.9 evidence required')
        require(driver.receipt.get('fixtureQualification', {}).get('candidate-full', {}).get('classAttributionQualified') is True, 'Original native class attribution proof required')
        from procurement_native_injections import run as run_injections
        os.environ['GITHUB_ACTIONS'] = 'false'
        os.environ['TESTCONTAINERS_RYUK_DISABLED'] = 'true'
        os.environ['MSBUILDDISABLENODEREUSE'] = '1'
        try:
            run_injections(driver, root / 'candidate')
        finally:
            driver.finish()
        return
    if args.phase == 'full':
        shared = Path(args.shared_checkout)
        cwd = root / 'candidate'
        require(re.fullmatch('[0-9a-f]{40}', args.shared_sha), "Integrity guard: re.fullmatch('[0-9a-f]{40}', args.shared_sha)")
        _, head = driver.command('shared-identity', ['git', 'rev-parse', 'HEAD'], shared, 10)
        require(head.strip() == args.shared_sha, 'Integrity guard: head.strip() == args.shared_sha')
        require(args.shared_sha != 'e3a6093324a24968876782153286f52db8b29fd8', "Integrity guard: args.shared_sha != 'e3a6093324a24968876782153286f52db8b29fd8'")
        os.environ['GITHUB_ACTIONS'] = 'false'
        os.environ['TESTCONTAINERS_RYUK_DISABLED'] = 'true'
        os.environ['MSBUILDDISABLENODEREUSE'] = '1'
        action = (shared / 'actions/dotnet-validate/action.yml').read_text()
        spec = install_spec(action)
        require(spec['env']['GOTOOLCHAIN'] == 'go1.26.9', 'Qualified Go1.26.9 scanner prerequisite required')
        apply_go_spec(os.environ, spec)
        driver.receipt['reviewedGoStep'] = {'stepSha256': spec['stepSha256'], 'package': spec['package'], 'GOTOOLCHAIN': spec['env']['GOTOOLCHAIN']}
        driver.save()
        try:
            mem = re.search('MemAvailable:\\s+(\\d+)', Path('/proc/meminfo').read_text())
            require(mem and int(mem.group(1)) >= 4194304, 'Integrity guard: mem and int(mem.group(1)) >= 4194304')
            _, effective = driver.command('effective-go-toolchain', ['go', 'env', 'GOTOOLCHAIN'], cwd, 15)
            require(effective.strip() == spec['env']['GOTOOLCHAIN'], 'Go discarded reviewed toolchain environment')
            _, version = driver.command('effective-go-version', ['go', 'version'], cwd, 15)
            driver.receipt['effectiveGoVersion'] = version.strip()
            require(version.strip().startswith('go version go1.26.9 '), 'Actual scanner toolchain differs')
            driver.save()
            driver.command('install-reviewed-gitleaks', ['go', 'install', spec['package']], cwd, 240)
            _, gopath = driver.command('go-path', ['go', 'env', 'GOPATH'], cwd, 15)
            gitleaks = str(Path(gopath.strip()) / 'bin/gitleaks')
            driver.command('gitleaks', ['gitleaks' if not Path(gitleaks).exists() else gitleaks, 'dir', str(cwd), '--redact', '--report-format', 'json', '--report-path', str(root / 'gitleaks.json')], cwd, 60)
            for script in ('Invoke-JwtSigningResourceScan.ps1', 'Invoke-CurrentTreeCredentialScan.ps1'):
                file = shared / 'scripts' / script
                require(file.is_file(), 'Integrity guard: file.is_file()')
                driver.command(script, ['pwsh', '-NoProfile', '-File', str(file), '-RepositoryPath', str(cwd)], cwd, 120)
            results = root / 'full-results'
            results.mkdir()
            full_roster = observe_roster(driver, 'candidate-full', cwd)
            require(full_roster['filter'] is None, 'Full roster/run must have no filter')
            associated_roster(full_roster, full=True)
            driver.begin_fixture_phase('candidate-full')
            driver.command('candidate-full', common_test_args(cwd, settings(root)) + ['-p:VSTestTestCaseFilter=', '--collect', 'XPlat Code Coverage', '--logger', 'trx;LogFileName=full.trx', '--results-directory', str(results)], cwd, 720, monitor=True)
            driver.command('candidate-coverage', ['python3', '-B', 'scripts/verify-runner-coverage.py', str(results)], cwd, 30)
            require(json.loads((root / 'gitleaks.json').read_bytes()) == [], "Integrity guard: json.loads((root / 'gitleaks.json').read_bytes()) == []")
            driver.command('candidate-format', ['dotnet', 'format', 'Legacy.Maliev.ProcurementService.slnx', '--verify-no-changes', '--no-restore'], cwd, 180)
            _, raw = driver.command('candidate-audit', ['dotnet', 'package', 'list', 'Legacy.Maliev.ProcurementService.slnx', '--vulnerable', '--include-transitive', '--no-restore', '--format', 'json', '--output-version', '1'], cwd, 60)
            data = json.loads(raw)
            require(type(data.get('version')) is int and data['version'] == 1, "Integrity guard: type(data.get('version')) is int and data['version'] == 1")
            require(not set(data) - {'version', 'parameters', 'sources', 'projects', 'logs'}, "Integrity guard: not set(data) - {'version', 'parameters', 'sources', 'projects', 'logs'}")
            require(data.get('logs', []) == [] and data.get('parameters') == '--vulnerable --include-transitive' and (data.get('sources') == ['https://api.nuget.org/v3/index.json']), "Integrity guard: data.get('logs', []) == [] and data.get('parameters') == '--vulnerable --include-transitive' and (data.get('sources') == ['https://api.nuget.org/v3/index.json'])")
            expected = {str(file.resolve()) for file in cwd.glob('Legacy.Maliev.ProcurementService.*/*.csproj')}
            projects = data.get('projects')
            require(type(projects) is list, 'Integrity guard: type(projects) is list')
            actual = set()
            for project in projects:
                require(type(project) is dict and (not set(project) - {'path', 'frameworks'}), "Integrity guard: type(project) is dict and (not set(project) - {'path', 'frameworks'})")
                name = str(Path(project['path']).resolve())
                require(name in expected and name not in actual, 'Integrity guard: name in expected and name not in actual')
                actual.add(name)
                assets = json.loads((Path(name).parent / 'obj/project.assets.json').read_bytes())
                lock = json.loads((Path(name).parent / 'packages.lock.json').read_bytes())
                restore = assets['project']['restore']
                require(str(Path(restore['projectPath']).resolve()) == name, "Integrity guard: str(Path(restore['projectPath']).resolve()) == name")
                require(set(restore['sources']) == {'https://api.nuget.org/v3/index.json'} and restore['originalTargetFrameworks'] == ['net10.0'], "Integrity guard: set(restore['sources']) == {'https://api.nuget.org/v3/index.json'} and restore['originalTargetFrameworks'] == ['net10.0']")
                require(set(assets['targets']) == {'net10.0'} and set(lock['dependencies']) == {'net10.0'}, "Integrity guard: set(assets['targets']) == {'net10.0'} and set(lock['dependencies']) == {'net10.0'}")
                packages = {key.lower(): entry for key, entry in assets['libraries'].items() if entry['type'] == 'package'}
                locked = {key.lower() + '/' + entry['resolved'].lower(): entry for key, entry in lock['dependencies']['net10.0'].items() if entry['type'] != 'Project'}
                require(set(packages) == set(locked), 'Integrity guard: set(packages) == set(locked)')
                for key, entry in packages.items():
                    require(entry['sha512'] == locked[key]['contentHash'], "Integrity guard: entry['sha512'] == locked[key]['contentHash']")
                require({key.lower() for key, entry in assets['targets']['net10.0'].items() if entry['type'] == 'package'} == set(packages), "Integrity guard: {key.lower() for key, entry in assets['targets']['net10.0'].items() if entry['type'] == 'package'} == set(packages)")
                if 'frameworks' not in project:
                    pass
                else:
                    require(type(project['frameworks']) is list and project['frameworks'], "Integrity guard: type(project['frameworks']) is list and project['frameworks']")
                    for framework in project['frameworks']:
                        require(type(framework) is dict and (not set(framework) - {'framework', 'topLevelPackages', 'transitivePackages'}) and (framework['framework'] == 'net10.0'), "Integrity guard: type(framework) is dict and (not set(framework) - {'framework', 'topLevelPackages', 'transitivePackages'}) and (framework['framework'] == 'net10.0')")
                        for key in ('topLevelPackages', 'transitivePackages'):
                            require(type(framework.get(key, [])) is list and framework.get(key, []) == [], 'Integrity guard: type(framework.get(key, [])) is list and framework.get(key, []) == []')
            require(actual == expected, 'Integrity guard: actual == expected')
            require(binary_hashes(cwd) == full_roster['binaryHashes'], 'Full execution inputs drifted')
            proof = trx(results, full_roster)
            require(proof['actualCases'] == 410, 'Full terminal roster count differs')
            driver.finish_fixture_phase()
            driver.receipt['fullSuite'] = proof
            driver.save()
            classes = {method.attrib['className'].split(',')[0] for method in ET.parse(next(results.glob('*.trx'))).findall('.//t:TestMethod', NS)}
            for required in ('ProcurementControllerContractTests', 'ProcurementPostgresMigrationTests', 'ProcurementRuntimeParityTests', 'ProcurementPaginationSourceTests', 'ProcurementPaginationWireContractTests', 'ProcurementIndependentContactTests'):
                require(any((value.endswith('.' + required) for value in classes)), "Integrity guard: any((value.endswith('.' + required) for value in classes))")
        except BaseException as exc:
            driver.receipt.setdefault('firstFailure', type(exc).__name__)
            driver.save()
            raise
        finally:
            driver.finish()
        return
    prepare(args, driver)
    os.environ['GITHUB_ACTIONS'] = 'false'
    os.environ['TESTCONTAINERS_RYUK_DISABLED'] = 'true'
    os.environ['MSBUILDDISABLENODEREUSE'] = '1'
    try:
        for phase in ('baseline', 'candidate'):
            cwd = root / phase
            mem = re.search('MemAvailable:\\s+(\\d+)', Path('/proc/meminfo').read_text())
            require(mem and int(mem.group(1)) >= 4194304, 'Integrity guard: mem and int(mem.group(1)) >= 4194304')
            driver.command(phase + '-restore', ['dotnet', 'restore', PROJECT, '--disable-parallel', '--use-lock-file', '-p:NuGetAudit=true', '-p:NuGetAuditMode=all', '-p:RestoreIgnoreFailedSources=false'], cwd, 180)
            _, build = driver.command(phase + '-build', ['dotnet', 'build', PROJECT, '-c', 'Release', '--no-restore', '-m:1', '-nodeReuse:false', '-p:UseSharedCompilation=false', '-warnaserror'], cwd, 240)
            require(re.search('\\b0 Warning\\(s\\)', build) and re.search('\\b0 Error\\(s\\)', build), "Integrity guard: re.search('\\\\b0 Warning\\\\(s\\\\)', build) and re.search('\\\\b0 Error\\\\(s\\\\)', build)")
            results = root / (phase + '-results')
            results.mkdir()
            testfilter = BASELINE_FILTER if phase == 'baseline' else CANDIDATE_FILTER
            roster = observe_roster(driver, phase + '-focused', cwd, testfilter)
            require(len(roster['names']) == (16 if phase == 'baseline' else 94), 'Focused compiled roster differs')
            if phase == 'candidate':
                associated_roster(roster, full=False)
            else:
                baseline_roster(roster)
            driver.begin_fixture_phase(phase)
            before = set(driver.receipt['postgres'])
            code, _ = driver.command(phase + '-focused', common_test_args(cwd, settings(root)) + ['--filter', testfilter, '--logger', 'trx;LogFileName=focused.trx', '--results-directory', str(results)], cwd, 480, allow_failure=phase == 'baseline', monitor=True)
            healthy = [r for cid, r in driver.receipt['postgres'].items() if cid not in before and r.get('serverVersionNum')]
            driver.receipt['resourceAttribution'] = {'globallyHealthyCount': len(healthy), 'classAttributionQualified': False, 'nativeAccepted': False}
            require(len(healthy) >= 2, 'Integrity guard: len(healthy) >= 2')
            require(binary_hashes(cwd) == roster['binaryHashes'], 'Focused execution inputs drifted')
            proof = trx(results, roster, red=phase == 'baseline')
            require(proof['failed'] == (16 if phase == 'baseline' else 0), 'All selected behavioral baseline cases must fail; candidate must pass')
            require((code != 0) == (phase == 'baseline'), "Integrity guard: (code != 0) == (phase == 'baseline')")
            driver.finish_fixture_phase()
            driver.receipt['phases'][phase] = proof
            driver.save()
            driver.cleanup()
    except BaseException as exc:
        driver.receipt.setdefault('firstFailure', type(exc).__name__)
        driver.save()
        raise
    finally:
        driver.finish()
if __name__ == '__main__':
    main()
