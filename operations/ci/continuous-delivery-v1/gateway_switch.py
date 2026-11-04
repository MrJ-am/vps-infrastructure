"""Graceful routing between two installed configurations, not a deployment authority.

The protected installer supplies paths, hashes and the readiness verifier.
No request may supply a configuration, command, URL or verifier. Backends are
never stopped here: draining and artifact admission belong to the controller.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


class Gateway:
    def __init__(self, directory, configurations, nginx, verify, owner=0):
        self.directory = Path(directory)
        self.configurations = configurations
        self.nginx = str(nginx)
        self.verify = verify
        self.owner = owner
        require(set(configurations) == {'blue', 'green'}, 'SLOT_REGISTRY_REFUSED')
        require(Path(nginx).is_absolute(), 'NGINX_PATH_REFUSED')
        self.current = self.directory / 'nginx.conf'
        self.record = self.directory / 'transition.json'

    def private_directory(self):
        s = self.directory.lstat()
        require(stat.S_ISDIR(s.st_mode) and s.st_uid == self.owner
                and stat.S_IMODE(s.st_mode) == 0o755, 'GATEWAY_DIRECTORY_REFUSED')

    def configuration(self, slot):
        require(slot in self.configurations, 'SLOT_REFUSED')
        path, digest = self.configurations[slot]
        path = Path(path)
        require(path.is_absolute(), 'CONFIGURATION_PATH_REFUSED')
        s = path.lstat()
        require(stat.S_ISREG(s.st_mode) and s.st_uid == self.owner
                and not s.st_mode & 0o022 and s.st_nlink == 1
                and s.st_size <= 1024 * 1024, 'CONFIGURATION_METADATA_REFUSED')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'CONFIGURATION_HASH_REFUSED')
        return path

    def selected(self):
        s = self.current.lstat()
        require(stat.S_ISLNK(s.st_mode) and s.st_uid == self.owner, 'SELECTOR_REFUSED')
        target = os.readlink(self.current)
        choices = [slot for slot in self.configurations if str(self.configuration(slot)) == target]
        require(len(choices) == 1, 'SELECTOR_TARGET_REFUSED')
        return choices[0]

    def sync(self):
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def checkpoint(self, previous, target, phase):
        raw = json.dumps({'previous': previous, 'target': target, 'phase': phase}, sort_keys=True).encode()
        fd, name = tempfile.mkstemp(prefix='transition-', dir=self.directory)
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, self.record)
        self.sync()

    def select(self, slot):
        target = self.configuration(slot)
        fd, name = tempfile.mkstemp(prefix='selector-', dir=self.directory)
        os.close(fd)
        os.unlink(name)
        os.symlink(str(target), name)
        os.replace(name, self.current)
        self.sync()

    def command(self, args):
        result = subprocess.run([self.nginx, *args], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env={'LANG': 'C', 'LC_ALL': 'C'}, timeout=15)
        require(result.returncode == 0, 'NGINX_OPERATION_REFUSED')

    def reload(self):
        self.command(['-t', '-c', str(self.current)])
        self.command(['-s', 'reload', '-c', str(self.current)])

    def read_checkpoint(self):
        try:
            fd = os.open(self.record, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, 'rb') as f:
            s = os.fstat(f.fileno())
            require(stat.S_ISREG(s.st_mode) and s.st_uid == self.owner and s.st_nlink == 1
                    and stat.S_IMODE(s.st_mode) == 0o600 and s.st_size <= 1024, 'CHECKPOINT_REFUSED')
            raw = f.read(1025)
        value = json.loads(raw)
        require(type(value) is dict and set(value) == {'previous', 'target', 'phase'}
                and value['previous'] in self.configurations and value['target'] in self.configurations
                and value['previous'] != value['target']
                and value['phase'] in ('intent', 'selected', 'committed', 'returned'), 'CHECKPOINT_REFUSED')
        return value

    def recover_locked(self):
        value = self.read_checkpoint()
        if value is None:
            return
        if value['phase'] in ('committed', 'returned'):
            expected = value['target'] if value['phase'] == 'committed' else value['previous']
            require(self.selected() == expected, 'CHECKPOINT_SELECTOR_MISMATCH')
            self.verify(expected)
            return
        require(self.selected() in (value['previous'], value['target']), 'RECOVERY_SELECTOR_REFUSED')
        self.select(value['previous'])
        self.reload()
        self.verify(value['previous'])
        self.checkpoint(value['previous'], value['target'], 'returned')

    def locked(self, action):
        self.private_directory()
        fd = os.open(self.directory / 'lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            s = os.fstat(fd)
            require(stat.S_ISREG(s.st_mode) and s.st_uid == self.owner and s.st_nlink == 1
                    and stat.S_IMODE(s.st_mode) == 0o600, 'LOCK_REFUSED')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return action()
        finally:
            os.close(fd)

    def recover(self):
        return self.locked(self.recover_locked)

    def switch(self, expected, target):
        require(expected in self.configurations and target in self.configurations
                and expected != target, 'TRANSITION_REFUSED')

        def transition():
            self.recover_locked()
            require(self.selected() == expected, 'STALE_ROUTE')
            self.command(['-t', '-c', str(self.configuration(target))])
            self.checkpoint(expected, target, 'intent')
            try:
                self.select(target)
                self.checkpoint(expected, target, 'selected')
                self.reload()
                self.verify(target)
                self.checkpoint(expected, target, 'committed')
            except Exception:
                self.select(expected)
                self.reload()
                self.verify(expected)
                self.checkpoint(expected, target, 'returned')
                raise
        return self.locked(transition)
