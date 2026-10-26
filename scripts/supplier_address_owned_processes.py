"""Retain pidfds for members of one task-created Linux session; never kill by name."""
import datetime
import os
import pathlib
import select
import signal
import subprocess
import sys
import time


def require(value, message):
    if not value:
        raise ValueError(message)


def process_identity(process_id):
    directory = pathlib.Path('/proc') / str(process_id)
    fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
    boot = next(int(line.split()[1]) for line in pathlib.Path('/proc/stat').read_text().splitlines() if line.startswith('btime '))
    try:
        executable = os.readlink(directory / 'exe')
    except FileNotFoundError:
        if fields[0] != 'Z':
            raise
        executable = None
    started = boot + int(fields[19]) / os.sysconf('SC_CLK_TCK')
    return {'processId':process_id, 'actualStartTimeUtc':datetime.datetime.fromtimestamp(started,datetime.timezone.utc).isoformat(),
            'executable':executable, 'startClockTicks':fields[19], 'state':fields[0],
            'parentId':int(fields[1]), 'processGroupId':int(fields[2]), 'sessionId':int(fields[3])}


def session_members(session_id):
    members = []
    for directory in pathlib.Path('/proc').glob('[0-9]*'):
        try:
            if directory.stat().st_uid != os.getuid():
                continue
            fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[3]) == session_id:
                members.append(process_identity(int(directory.name)))
        except FileNotFoundError:
            continue
    return members


def ready(fd):
    return bool(select.select([fd], [], [], 0)[0])


class OwnedSession:
    def __init__(self, process):
        require(sys.platform.startswith('linux') and hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'Linux pidfd custody is required')
        self.process = process
        self.leader = process_identity(process.pid)
        require(self.leader['sessionId'] == self.leader['processGroupId'] == process.pid, 'Launcher must create a new isolated session')
        self.handles = {}
        self.errors = []
        self.forced = False
        self.exited_before_binding = []

    def capture(self):
        members = session_members(self.process.pid)
        leader = next((x for x in members if x['processId'] == self.process.pid), None)
        require(leader is None or leader['startClockTicks'] == self.leader['startClockTicks'], 'Session leader PID was reused; preserve uncertain resources')
        for member in members:
            require(int(member['startClockTicks']) >= int(self.leader['startClockTicks']), 'Unproven session member birth')
            process_id = member['processId']
            known = self.handles.get(process_id)
            if known is not None:
                require(known['identity']['startClockTicks'] == member['startClockTicks'], 'Member PID was reused; never signal it')
                continue
            if self.handles and all(ready(value['fd']) for value in self.handles.values()):
                require(leader is not None and leader['startClockTicks'] == self.leader['startClockTicks'], 'Cannot attribute a new member after every retained owner exited')
            try:
                fd = os.pidfd_open(process_id, 0)
            except ProcessLookupError:
                self.exited_before_binding.append(member)
                continue
            try:
                try:
                    current = process_identity(process_id)
                except FileNotFoundError:
                    if ready(fd):
                        self.exited_before_binding.append(member)
                        os.close(fd)
                        continue
                    raise
                require(current['sessionId'] == self.process.pid and current['startClockTicks'] == member['startClockTicks'], 'Identity changed while opening pidfd')
                self.handles[process_id] = {'fd':fd, 'identity':current}
            except BaseException:
                os.close(fd)
                raise

    def _capture_safely(self):
        try:
            self.capture()
        except BaseException as error:
            self.errors.append('capture: ' + type(error).__name__ + ': ' + str(error))

    def _signal_live(self, value, leader_only=None):
        for record in sorted(self.handles.values(), key=lambda x:int(x['identity']['startClockTicks']), reverse=True):
            if leader_only is not None and (record['identity']['processId'] == self.process.pid) != leader_only:
                continue
            try:
                if not self._ready(record):
                    signal.pidfd_send_signal(record['fd'], value)
                    self.forced = True
            except (OSError, ValueError) as error:
                if not self._ready(record):
                    self.errors.append('signal: ' + type(error).__name__ + ': ' + str(error))

    def _ready(self, record):
        try:
            return ready(record['fd'])
        except (OSError, ValueError) as error:
            self.errors.append('pidfd state: ' + type(error).__name__ + ': ' + str(error))
            return False

    def _settle(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._capture_safely()
            if all(self._ready(record) for record in self.handles.values()):
                return
            time.sleep(0.05)

    def cleanup(self, failed=False):
        proof = {'leader':self.leader, 'members':[], 'cleanupErrors':[], 'verified':False, 'handlesClosed':False}
        remaining = None
        try:
            self._capture_safely()
            if not failed:
                self._settle(2)
            self._signal_live(signal.SIGTERM, leader_only=False)
            self._settle(1)
            self._signal_live(signal.SIGTERM, leader_only=True)
            self._settle(3)
            self._signal_live(signal.SIGKILL)
            self._settle(3)
            try:
                self.process.wait(timeout=3)
            except (OSError, subprocess.SubprocessError) as error:
                self.errors.append('wait: ' + type(error).__name__ + ': ' + str(error))
            try:
                remaining = session_members(self.process.pid)
                deadline = time.monotonic() + 2
                while remaining and time.monotonic() < deadline and all(self._ready(record) for record in self.handles.values()):
                    time.sleep(0.05)
                    remaining = session_members(self.process.pid)
            except (OSError, ValueError) as error:
                self.errors.append('terminal observation: ' + type(error).__name__ + ': ' + str(error))
            proof['members'] = [dict(record['identity'], exited=self._ready(record)) for record in self.handles.values()]
            proof['remainingSessionMembers'] = remaining
            proof['launcherExited'] = self.process.poll() is not None
            proof['forcedCleanup'] = self.forced
            proof['verified'] = remaining == [] and proof['launcherExited'] and all(row['exited'] for row in proof['members']) and not self.errors
        except BaseException as error:
            self.errors.append('cleanup: ' + type(error).__name__ + ': ' + str(error))
        finally:
            close_errors = []
            for record in self.handles.values():
                try:
                    os.close(record['fd'])
                except OSError as error:
                    close_errors.append('close: ' + type(error).__name__ + ': ' + str(error))
            proof['handlesClosed'] = not close_errors
            self.errors.extend(close_errors)
            proof['cleanupErrors'] = list(self.errors)
            proof['exitedBeforeBinding'] = list(self.exited_before_binding)
            proof['verified'] = proof['verified'] and not self.errors
        return proof
