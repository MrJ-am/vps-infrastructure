#!/usr/bin/env python3
"""Offline credential adaptation. No network, legacy execution or secret output."""
import base64
import fcntl
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parent
INPUT = Path('/run/mrjam-worker-credential-adaptation')
STATE = Path('/var/lib/mrjam-worker-credentials')
DESTINATION = 'v1'
PENDING = '.v1.pending'
SOURCE_NAMES = ('proton-smtp.json', 'cycle.json', 'fermeture-hook.secret')
OUTPUT_NAMES = frozenset(('smtp.json', 'recipient', 'closure', 'approval',
                          'archive.json', 'archive-initialize.json'))
SECRET = re.compile(r'[A-Za-z0-9_-]{43}')
AGE = re.compile(r'age1[a-z0-9]{58}')
SQL_NAME = re.compile(r'[a-z][a-z0-9_]{0,62}')
STORE_AGE = re.compile(r'/nix/store/[a-z0-9]{32}-[A-Za-z0-9+._?=-]+/bin/age')


class Refused(Exception):
    """Only a fixed error code may escape the executable."""


def strict_json(raw):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 65536:
        raise Refused()

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Refused()
            result[key] = value
        return result

    def constant(_):
        raise Refused()

    value = json.loads(raw.decode('utf-8'), object_pairs_hook=object_pairs,
                       parse_constant=constant)
    if type(value) is not dict:
        raise Refused()
    return value


def encode(value):
    raw = (json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False)+'\n').encode()
    if len(raw) > 8192:
        raise Refused()
    return raw


def address(value):
    if not isinstance(value, str) or len(value.encode()) > 254 or value.count('@') != 1:
        return False
    local, domain = value.split('@')
    if '.' not in domain:
        return False
    base, tld = domain.rsplit('.', 1)
    return bool(re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
                and re.fullmatch(r'[A-Za-z0-9.-]+', base)
                and re.fullmatch(r'[A-Za-z]{2,63}', tld))


def public_configuration(raw):
    value = strict_json(raw)
    if set(value) != {'journal_database', 'age_program'}:
        raise Refused()
    name, age = value['journal_database'], value['age_program']
    if not isinstance(name, str) or not SQL_NAME.fullmatch(name) or name.startswith('pg_') or name in ('postgres', 'template0', 'template1', 'all', 'replication'):
        raise Refused()
    if not isinstance(age, str) or not STORE_AGE.fullmatch(age):
        raise Refused()
    return value


def convert(smtp_bytes, cycle_bytes, closure_bytes, public):
    public = public_configuration(encode(public))
    smtp = strict_json(smtp_bytes)
    if set(smtp) != {'host', 'port', 'username', 'password', 'from_address', 'starttls_required', 'certificate_verification'}:
        raise Refused()
    if (smtp['host'] != 'smtp.protonmail.ch' or type(smtp['port']) is not int or smtp['port'] != 587
            or smtp['starttls_required'] is not True or smtp['certificate_verification'] is not True
            or not isinstance(smtp['password'], str) or not re.fullmatch(r'[A-Za-z0-9]{16,128}', smtp['password'])
            or not address(smtp['username']) or not address(smtp['from_address'])
            or smtp['username'].lower() != smtp['from_address'].lower()):
        raise Refused()
    cycle = strict_json(cycle_bytes)
    if set(cycle) != {'recipient_age', 'adresse_exploitant'} or not address(cycle['adresse_exploitant']):
        raise Refused()
    if not isinstance(cycle['recipient_age'], str) or not AGE.fullmatch(cycle['recipient_age']):
        raise Refused()
    if not isinstance(closure_bytes, bytes) or not 1 <= len(closure_bytes) <= 128:
        raise Refused()
    # Match the legacy secret reader's documented surrounding whitespace only.
    closure = closure_bytes.decode('utf-8').strip(' \t\r\n')
    if not SECRET.fullmatch(closure):
        raise Refused()
    outputs = {'smtp.json': encode(smtp),
               'recipient': (cycle['adresse_exploitant']+'\n').encode(),
               'closure': (closure+'\n').encode()}
    for suffix in ('', '-initialize'):
        unit = 'mrjam-vision-archive'+suffix+'.service'
        outputs['archive'+suffix+'.json'] = encode({
            'schema_version': 1, 'journal_database': public['journal_database'],
            'state_file': '/var/lib/mrjam-vision-archive/courriels.sqlite',
            'smtp_file': f'/run/credentials/{unit}/smtp',
            'recipient_file': f'/run/credentials/{unit}/recipient',
            'age_program': public['age_program'], 'age_recipient': cycle['recipient_age'],
        })
    return outputs


def open_directory(path):
    path = Path(path)
    if not path.is_absolute() or any(p in ('.', '..') for p in str(path).split('/')):
        raise Refused()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for name in path.parts[1:]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def private_directory(fd):
    meta = os.fstat(fd)
    if meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) != 0o700:
        raise Refused()


def entries(fd):
    # Directory descriptors are reused after additions. Rewind explicitly;
    # a previous enumeration may otherwise hide newly created entries.
    os.lseek(fd, 0, os.SEEK_SET)
    return set(os.listdir(fd))


def read_file(directory, name, maximum, *, sealed=False):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
    try:
        before = os.fstat(fd)
        expected_mode = 0o440 if sealed else 0o600
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != expected_mode
                or not 1 <= before.st_size <= maximum):
            raise Refused()
        if sealed and (before.st_gid != 0 or not (os.fstatvfs(fd).f_flag & os.ST_RDONLY)):
            raise Refused()
        chunks = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise Refused()
        result = b''.join(chunks)
        if len(result) != before.st_size:
            raise Refused()
        return result
    finally:
        os.close(fd)


def sealed_inputs():
    fd = open_directory(INPUT)
    try:
        private_directory(fd)
        if entries(fd) != set(SOURCE_NAMES):
            raise Refused()
        return tuple(read_file(fd, name, 128 if name.endswith('.secret') else 65536, sealed=True)
                     for name in SOURCE_NAMES)
    finally:
        os.close(fd)


def valid_approval(raw, closure):
    try:
        text = raw.decode('ascii')
    except (UnicodeError, AttributeError):
        return False
    return bool(text.endswith('\n') and SECRET.fullmatch(text[:-1]) and not hmac.compare_digest(raw, closure))


def new_approval(closure):
    for _ in range(4):
        raw = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=')+b'\n'
        if valid_approval(raw, closure):
            return raw
    raise Refused()


def create_file(directory, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def verify_contents(fd, outputs, *, complete):
    private_directory(fd)
    present = entries(fd)
    if not present <= OUTPUT_NAMES or (complete and present != OUTPUT_NAMES):
        raise Refused()
    for name in present:
        raw = read_file(fd, name, 8192)
        if name == 'approval':
            if not valid_approval(raw, outputs['closure']):
                raise Refused()
        elif not hmac.compare_digest(raw, outputs[name]):
            raise Refused()
    return present


def publish(directory, outputs):
    if set(outputs) != OUTPUT_NAMES - {'approval'}:
        raise Refused()
    parent = open_directory(directory)
    try:
        private_directory(parent)
        fcntl.flock(parent, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # This private root-owned parent is not writable by any worker. The lock
        # serializes this sole publisher; no existing generation is replaced.
        if DESTINATION in entries(parent):
            fd = os.open(DESTINATION, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            try:
                verify_contents(fd, outputs, complete=True)
            finally:
                os.close(fd)
            if PENDING in entries(parent):
                raise Refused()
            return
        try:
            os.mkdir(PENDING, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
        pending = os.open(PENDING, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        try:
            present = verify_contents(pending, outputs, complete=False)
            if 'approval' not in present:
                create_file(pending, 'approval', new_approval(outputs['closure']))
            for name in sorted(outputs):
                if name not in present:
                    create_file(pending, name, outputs[name])
            verify_contents(pending, outputs, complete=True)
            os.fsync(pending)
        finally:
            os.close(pending)
        os.rename(PENDING, DESTINATION, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)


def main():
    try:
        if len(sys.argv) != 1 or os.geteuid() != 0:
            raise Refused()
        os.umask(0o077)
        public = public_configuration((ROOT/'public.json').read_bytes())
        outputs = convert(*sealed_inputs(), public)
        publish(STATE, outputs)
        print('{"status":"prepared"}')
    except Exception:
        print('{"error":"CREDENTIAL_ADAPTATION_REFUSED"}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
