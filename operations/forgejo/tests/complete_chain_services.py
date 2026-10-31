#!/usr/bin/env python3
"""Disposable Cloud socket activation fixture; never a production listener.

Run unchanged worker/collector entrypoints under distinct UIDs. The root
listener owns only the accepted descriptor and the fixed child identity.
No candidate can select a command, path, UID or namespace configuration.
"""
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading

PYTHON = '/nix/store/kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-python3-3.13.17/bin/python3'
FIXTURE = Path('/fixture')


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def write_root(path, value, mode=0o444):
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    with path.open('x') as out:
        out.write(json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n')
    path.chmod(mode)


def demote(uid):
    def apply():
        os.setsid()
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
    return apply


class SocketService:
    def __init__(self, path, group, uid, program, *, status=None, receipt_only=False):
        require(os.getuid() == 0 and set(os.listdir('/sys/class/net')) == {'lo'}, 'OFFLINE_FIXTURE_REQUIRED')
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        require(not self.path.exists(), 'SOCKET_COLLISION')
        self.listener = socket.socket(socket.AF_UNIX)
        self.listener.bind(str(self.path))
        os.chown(self.path, 0, group)
        self.path.chmod(0o660)
        self.listener.listen(2)
        self.listener.settimeout(0.2)
        self.uid, self.program, self.status = uid, program, status
        self.receipt_only = receipt_only
        self.fixed_errors = []
        self.calls = 0
        self.codes = []
        self.error = False
        self.child = None
        self.stopped = threading.Event()
        self.report()
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def report(self):
        if self.status is not None:
            temporary = self.status.with_suffix('.tmp')
            value = {'calls': self.calls, 'exit_codes': self.codes, 'error': self.error, 'uid': self.uid}
            if self.receipt_only:
                value['fixed_errors'] = self.fixed_errors
            temporary.write_text(json.dumps(value, sort_keys=True)+'\n')
            temporary.chmod(0o444)
            os.replace(temporary, self.status)

    def serve(self):
        try:
            while not self.stopped.is_set():
                try:
                    connection, _ = self.listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    return
                with connection:
                    self.calls += 1
                    self.report()
                    with tempfile.TemporaryFile() as response:
                        self.child = subprocess.Popen([PYTHON, '-I', '-S', self.program],
                            stdin=connection, stdout=response if self.receipt_only else connection,
                            stderr=subprocess.DEVNULL, start_new_session=True, user=self.uid,
                            group=self.uid, extra_groups=[], close_fds=True,
                            env={'PATH': '/bin', 'LANG': 'C.UTF-8', 'HOME': '/tmp'})
                        self.codes.append(self.child.wait(timeout=1845))
                        if self.receipt_only:
                            response.seek(0)
                            raw = response.read(4097)
                            require(len(raw) <= 4096, 'COLLECTOR_RECEIPT_LIMIT')
                            value = json.loads(raw)
                            if value.get('decision') == 'reject' and re.fullmatch(r'[A-Z_]{1,80}', value.get('code', '')):
                                self.fixed_errors.append(value['code'])
                            connection.sendall(raw)
                    self.child = None
                    self.report()
        except Exception:
            self.error = True
            self.report()

    def close(self):
        self.stopped.set()
        self.listener.close()
        if self.child is not None and self.child.poll() is None:
            os.killpg(self.child.pid, signal.SIGKILL)
            self.child.wait(timeout=10)
        self.thread.join(timeout=10)
        self.path.unlink(missing_ok=True)


def worker():
    require(len(sys.argv) == 2 and sys.argv[1] == 'worker' and os.getuid() == 0 and
            set(os.listdir('/sys/class/net')) == {'lo'}, 'OFFLINE_WORKER_FIXTURE_REQUIRED')
    limits = {n: Path('/sys/fs/cgroup', n).read_text().strip()
              for n in ('memory.max', 'pids.max', 'cpu.max')}
    quota, period = map(int, limits['cpu.max'].split())
    require(limits['memory.max'] == str(2*1024**3) and limits['pids.max'] == '256'
            and quota == period, 'WORKER_CGROUP_CHANGED')
    record = json.loads((FIXTURE/'runtime.json').read_bytes())
    write_root(Path('/etc/mrjam-validation-worker/policy.json'), record['configuration'])
    lock = Path('/run/mrjam-validation-worker/operation.lock')
    lock.parent.mkdir(mode=0o755)
    with lock.open('x'):
        pass
    os.chown(lock, 0, 59990)
    lock.chmod(0o440)
    service = SocketService('/run/mrjam-validation/request.sock', 59991, 59990,
        '/fixture/code/forgejo/worker.py', status=Path('/run/mrjam-validation/worker-status.json'))
    write_root(Path('/run/mrjam-validation/ready.json'), {'worker_cgroup': limits,
        'worker_uid': 59990, 'network_interfaces': ['lo'], 'production_access': False})
    try:
        while service.thread.is_alive() and not service.error:
            service.stopped.wait(1)
        require(False, 'WORKER_LISTENER_STOPPED')
    finally:
        service.close()


if __name__ == '__main__':
    worker()
