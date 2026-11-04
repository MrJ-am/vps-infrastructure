"""Fixed local entrypoints for capture and restart recovery; no restore API."""
import fcntl
import http.client
import json
import os
import re
from pathlib import Path
import stat
import sys
import time
import capture as C
import envelope as E
import transaction as T
import retention as R

ROOT = Path('/var/backup/mrjam/vise-v1')
STATE = Path('/var/lib/mrjam-vise-backup')
LOCK = Path('/var/lib/mrjam-cutover/first-deployment/transaction.lock')


class Adapter:
    def __init__(self, tools):
        self.snapshot = C.Snapshot(tools, ROOT)
        self.envelope = E.Envelope(tools)
        C.directory(STATE, 0)
        C.directory(ROOT, 0)

    def read(self):
        path = STATE / 'state.json'
        if not path.exists() and not path.is_symlink():
            return None
        fd, _ = C.regular(path, 0, 16384)
        with os.fdopen(fd, 'rb') as source:
            return T.checked(json.load(source))

    def save(self, value):
        T.checked(value)
        pending = STATE / 'state.next'
        if pending.exists() or pending.is_symlink():
            fd, _ = C.regular(pending, 0, 16384)
            os.close(fd)
            pending.unlink()
        E.write_json(pending, value)
        os.replace(pending, STATE / 'state.json')
        C.sync(STATE)

    def preflight(self):
        # Validate the recipient before stopping the application. The value
        # stays inside this root process and is never printed or persisted.
        credential = Path(os.environ['CREDENTIALS_DIRECTORY']) / 'archive-configuration'
        fd = os.open(credential, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            C.require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) in {0o400, 0o600} and info.st_size <= 8192,
                'VISE_BACKUP_CREDENTIAL_REFUSED')
            value = json.load(source)
        self.recipient = value.get('age_recipient') if type(value) is dict else None
        C.require(type(self.recipient) is str and E.AGE.fullmatch(self.recipient),
                  'VISE_BACKUP_RECIPIENT_REFUSED')
        self.snapshot.preflight()

    def active(self):
        result = self.snapshot.run([self.snapshot.tools['systemctl'], 'show', 'vise.service',
                                    '-p', 'ActiveState', '--value'], capture=True).strip()
        C.require(result in {b'active', b'inactive'}, 'VISE_BACKUP_SERVICE_TRANSITION')
        return result == b'active'

    def identifier(self):
        return os.urandom(16).hex()

    def stop(self):
        self.snapshot.run([self.snapshot.tools['systemctl'], 'stop', 'vise.service'], timeout=180)

    def start(self):
        self.snapshot.run([self.snapshot.tools['systemctl'], 'start', 'vise.service'], timeout=90)

    def ready(self):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            connection = http.client.HTTPConnection('127.0.0.1', 3017, timeout=5)
            try:
                connection.request('GET', '/api/health')
                response = connection.getresponse()
                raw = response.read(1025)
                if response.status == 200 and len(raw) <= 1024 and json.loads(raw) == {'status': 'ok', 'prototype': True}:
                    C.require(self.active(), 'VISE_BACKUP_RESTART_NOT_ACTIVE')
                    return
            except (OSError, ValueError, http.client.HTTPException):
                pass
            finally:
                connection.close()
            time.sleep(1)
        raise C.Refused('VISE_BACKUP_RESTART_NOT_READY')

    def offline(self):
        self.snapshot.offline()

    def capture(self, identifier):
        work = ROOT / ('.' + identifier + '.pending')
        work.mkdir(mode=0o700)
        components = work / 'components'
        components.mkdir(mode=0o700)
        C.sync(work)
        C.sync(ROOT)
        self.snapshot.capture(components)

    def verify(self, identifier):
        self.snapshot.verify(ROOT / ('.' + identifier + '.pending') / 'components')

    def publish(self, identifier):
        self.envelope.publish(ROOT, identifier, self.recipient)


def main():
    C.require(os.getuid() == 0 and len(sys.argv) == 2 and sys.argv[1] in {'capture', 'recover'},
              'VISE_BACKUP_ENTRYPOINT_REFUSED')
    os.umask(0o077)
    fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        C.require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
            and stat.S_IMODE(info.st_mode) == 0o600, 'VISE_BACKUP_LOCK_REFUSED')
        # A generation switch can start this recovery unit while its caller
        # owns the deployment lock. Never wait back on that caller: the
        # persistent recovery timer retries after the deployment releases it.
        # Deferral touches neither the journal nor application data/services.
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if sys.argv[1] == 'recover':
                print(json.dumps({'code': 'VISE_BACKUP_RECOVERY_DEFERRED'}))
                return
            raise C.Refused('VISE_BACKUP_ENVIRONMENT_BUSY') from None
        adapter = Adapter(json.loads('@commands_json@'))
        result = T.capture(adapter) if sys.argv[1] == 'capture' else T.recover(adapter)
        if result == 'VISE_BACKUP_COMPLETE':
            # Availability is already restored, and the new encrypted pair is
            # durable. Retention never runs after a failed or resumed capture.
            R.prune(ROOT, adapter.read()['capture_id'])
        print(json.dumps({'code': result}))
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        code = str(error) if isinstance(error, C.Refused) and re.fullmatch('VISE_[A-Z_]{1,80}', str(error)) else 'VISE_BACKUP_REFUSED'
        print(json.dumps({'code': code, 'exception_type': type(error).__name__}))
        raise SystemExit(1) from None
