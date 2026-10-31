#!/usr/bin/env python3
"""Fixed offline adoption of sealed legacy admission snapshots. No network/SQL API."""
import fcntl
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time

MAX_SOURCE = 64 * 1024**2
MAX_TARGET = 128 * 1024**2
MAX_ROWS = 10000
ROOT = Path(__file__).resolve().parent
INPUT = Path('/run/mrjam-admission-adoption')
STATE = Path('/var/lib/mrjam-vision-admission')
DESTINATION = 'admissions.sqlite'
PENDING = '.admission-adoption.pending.sqlite'
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
HASH = re.compile(r'[0-9a-f]{64}')


class Refused(Exception):
    """The CLI never emits details from an input, SQLite or the filesystem."""


def schema(name):
    return (ROOT / 'schemas' / name).read_text()


def connection(raw=None):
    db = sqlite3.connect(':memory:')
    db.enable_load_extension(False)
    db.execute('PRAGMA trusted_schema=OFF')
    db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 256 * 1024)
    deadline = time.monotonic() + 15
    remaining = [10000]
    def progress():
        remaining[0] -= 1
        return int(remaining[0] < 0 or time.monotonic() > deadline)
    db.set_progress_handler(progress, 1000)
    if raw is not None:
        if not 100 <= len(raw) <= MAX_TARGET or raw[:16] != b'SQLite format 3\0' or raw[18:20] != b'\1\1':
            db.close()
            raise Refused()
        db.deserialize(raw)
        db.execute('PRAGMA query_only=ON')
    return db


def objects(db):
    return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def reference(mail=False, with_hash=False, target=False):
    db = connection()
    if target:
        db.executescript(schema('target-mail.sql') + schema('target-requests.sql'))
    else:
        db.executescript(schema('legacy-mail.sql' if mail else 'legacy-requests.sql'))
        if with_hash:
            db.execute('ALTER TABLE courriels ADD COLUMN empreinte TEXT')
    return db


def inspect(raw, mail=False, target=False):
    if not target and len(raw) > MAX_SOURCE:
        raise Refused()
    db = connection(raw)
    try:
        permitted = []
        for with_hash in ([False, True] if mail and not target else [False]):
            model = reference(mail, with_hash, target)
            try:
                permitted.append(objects(model))
            finally:
                model.close()
        # No views, triggers, unknown indexes, virtual tables or altered schema.
        if objects(db) not in permitted or db.execute('PRAGMA integrity_check(1)').fetchone() != ('ok',):
            raise Refused()
        return db
    except Exception:
        db.close()
        raise


def rows(db, table):
    # Identifiers below come only from this program's closed choices/model.
    if table not in ('demandes', 'courriels'):
        raise Refused()
    key = 'id' if table == 'demandes' else 'cle'
    values = db.execute(f'SELECT * FROM {table} ORDER BY {key} COLLATE BINARY LIMIT 10001').fetchall()
    if len(values) > MAX_ROWS:
        raise Refused()
    columns = db.execute(f'PRAGMA table_info({table})').fetchall()
    for row in values:
        for value, (_, _, kind, required, _, _) in zip(row, columns, strict=True):
            if value is None:
                if required:
                    raise Refused()
            elif (kind == 'INTEGER' and type(value) is not int) or (kind == 'TEXT' and type(value) is not str) or (kind == 'BLOB' and type(value) is not bytes):
                raise Refused()
            elif isinstance(value, str) and len(value.encode()) > 8192:
                raise Refused()
    return [c[1] for c in columns], values


def merge(requests, mail):
    source_requests = inspect(requests)
    source_mail = None
    destination = None
    try:
        source_mail = inspect(mail, mail=True)
        destination = reference(target=True)
        request_names, request_rows = rows(source_requests, 'demandes')
        mail_names, mail_rows = rows(source_mail, 'courriels')
        ids = set()
        for row in request_rows:
            p = dict(zip(request_names, row, strict=True))
            if not isinstance(p['id'], str) or not UUID.fullmatch(p['id']) or not HASH.fullmatch(p['invitation']):
                raise Refused()
            if p['etat'] not in ('attente', 'provisionnee', 'admise', 'expiree') or any(p[name] not in (0, 1) for name in ('parental', 'manuel', 'nouvel_utilisateur')):
                raise Refused()
            if any(p[name] is not None and (type(p[name]) is not int or p[name] < 0) for name in ('cree', 'expire', 'verifie_a', 'accord_a', 'controle_a', 'terminee')):
                raise Refused()
            if any(p[name] is not None and not HASH.fullmatch(p[name]) for name in ('verification', 'accord')):
                raise Refused()
            ids.add(p['id'])
        copied_mail = []
        for row in mail_rows:
            p = dict(zip(mail_names, row, strict=True))
            if not isinstance(p['cle'], str):
                raise Refused()
            prefix, separator, identifier = p['cle'].partition(':')
            if not separator or prefix not in ('admission', 'parent', 'admis') or not UUID.fullmatch(identifier):
                raise Refused()
            if p['etat'] not in ('attente', 'accepte_relais', 'annule') or len(p['message']) > 131072:
                raise Refused()
            if identifier not in ids and (p['message'] or p['etat'] == 'attente'):
                raise Refused()
            if any(type(p[name]) is not int or p[name] < 0 for name in ('cree', 'essais', 'prochain')):
                raise Refused()
            if p['accepte'] is not None and (type(p['accepte']) is not int or p['accepte'] < 0):
                raise Refused()
            digest = p.get('empreinte')
            if digest is not None and (not HASH.fullmatch(digest) or (p['message'] and hashlib.sha256(p['message']).hexdigest() != digest)):
                raise Refused()
            # Opaque message, original hash, state and retry dates are preserved.
            copied_mail.append(tuple(p[name] for name in ('cle', 'message', 'cree', 'etat', 'essais', 'prochain', 'accepte', 'erreur')) + (digest, None))
        with destination:
            destination.executemany('INSERT INTO demandes VALUES(' + ','.join('?' for _ in request_names) + ')', request_rows)
            destination.executemany('INSERT INTO courriels VALUES(?,?,?,?,?,?,?,?,?,?)', copied_mail)
        result = destination.serialize()
        if len(result) > MAX_TARGET:
            raise Refused()
        return result
    finally:
        source_requests.close()
        if source_mail is not None:
            source_mail.close()
        if destination is not None:
            destination.close()


def equivalent(left, right):
    a = inspect(left, target=True)
    b = None
    try:
        b = inspect(right, target=True)
        return all(rows(a, table) == rows(b, table) for table in ('demandes', 'courriels'))
    finally:
        a.close()
        if b is not None:
            b.close()


def read_fd(fd, maximum):
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or not 100 <= before.st_size <= maximum:
        raise Refused()
    parts = []
    left = before.st_size + 1
    while left:
        block = os.read(fd, min(left, 1024 * 1024))
        if not block:
            break
        parts.append(block)
        left -= len(block)
    after = os.fstat(fd)
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise Refused()
    result = b''.join(parts)
    if len(result) != before.st_size:
        raise Refused()
    return result


def sealed_input(name):
    if name not in ('requests.sqlite', 'mail.sqlite'):
        raise Refused()
    parent = os.open(INPUT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        meta = os.fstat(parent)
        if meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) != 0o700:
            raise Refused()
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        try:
            meta = os.fstat(fd)
            if meta.st_uid != 0 or meta.st_gid != os.getegid() or stat.S_IMODE(meta.st_mode) != 0o440 or meta.st_nlink != 1 or not (os.fstatvfs(fd).f_flag & os.ST_RDONLY):
                raise Refused()
            return read_fd(fd, MAX_SOURCE)
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def private_existing(directory, name, links=1):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    except FileNotFoundError:
        return None
    try:
        meta = os.fstat(fd)
        if meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) != 0o600 or meta.st_nlink != links:
            raise Refused()
        return meta.st_dev, meta.st_ino, read_fd(fd, MAX_TARGET)
    finally:
        os.close(fd)


def publish(directory, result):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        meta = os.fstat(fd)
        if meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) != 0o700:
            raise Refused()
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Recover the sole two-link window after atomic no-replace publication.
        try:
            old = os.stat(DESTINATION, dir_fd=fd, follow_symlinks=False)
            temp = os.stat(PENDING, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            old = temp = None
        if old is not None and old.st_nlink == 2 and (old.st_dev, old.st_ino) == (temp.st_dev, temp.st_ino):
            installed = private_existing(fd, DESTINATION, links=2)
            if not equivalent(installed[2], result):
                raise Refused()
            os.unlink(PENDING, dir_fd=fd)
            os.fsync(fd)
            return
        installed = private_existing(fd, DESTINATION)
        pending = private_existing(fd, PENDING)
        if installed is not None:
            if pending is not None or not equivalent(installed[2], result):
                raise Refused()
            return
        if pending is None:
            temporary = os.open(PENDING, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=fd)
            try:
                with os.fdopen(temporary, 'wb', closefd=False) as stream:
                    stream.write(result)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                os.close(temporary)
        elif not equivalent(pending[2], result):
            raise Refused()
        os.link(PENDING, DESTINATION, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        os.unlink(PENDING, dir_fd=fd)
        os.fsync(fd)
    finally:
        os.close(fd)


def main():
    try:
        if len(sys.argv) != 1 or os.geteuid() == 0:
            raise Refused()
        os.umask(0o077)
        result = merge(sealed_input('requests.sqlite'), sealed_input('mail.sqlite'))
        publish(STATE, result)
        print('{"status":"adopted"}')
    except Exception:
        print('{"error":"ADMISSION_ADOPTION_REFUSED"}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
