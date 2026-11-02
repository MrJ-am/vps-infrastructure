#!/usr/bin/env python3
"""Closed, offline adoption of the native cycle and archival mail queues.

No installed legacy program is imported or executed. The two installed entry
points have distinct, build-time profiles and accept no command-line arguments.
"""
import fcntl
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time

PROFILE = None  # Fixed separately in each installed entry point.
ROOT = Path(__file__).resolve().parent
PROFILES = {
    'cycle': (Path('/run/mrjam-cycle-mail-adoption'), ('mail.sqlite',),
              Path('/var/lib/mrjam-vision-cycle')),
    'archive': (Path('/run/mrjam-archive-mail-adoption'),
                ('closure.sqlite', 'global.sqlite'),
                Path('/var/lib/mrjam-vision-archive')),
}
DESTINATION = 'courriels.sqlite'
PENDING = '.mail-adoption.pending.sqlite'
MAX_SOURCE = 64 * 1024**2
MAX_TARGET = 128 * 1024**2
MAX_ROWS = 10000
KEY = re.compile(r'[A-Za-z0-9_.:-]{1,160}')
HASH = re.compile(r'[0-9a-f]{64}')
IDENTIFIER = re.compile(r'[A-Za-z0-9_.-]{1,64}')
DDL_TOKEN = re.compile(r"(?P<quoted>'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`(?:[^`]|``)*`|\[[^\]]*\])|(?P<comment>--[^\r\n]*(?:\r?\n|$)|/\*.*?\*/)|(?P<word>[A-Za-z_][A-Za-z_0-9$]*)|(?P<number>[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?|\.[0-9]+(?:[eE][+-]?[0-9]+)?)|(?P<operator>!=|<>|<=|>=|==|<<|>>|\|\||->>|->|[(),.;=<>+*/%&|~\-])", re.S)
MARKERS = {
    'cycle': ('effacements_termines', 'utilisateur', 'cycle-markers.sql'),
    'closure': ('fermetures', 'sujet', 'closure-markers.sql'),
    'archive': ('fermetures', 'sujet', 'closure-markers.sql'),
}


class Refused(Exception):
    """The entry points never emit input, SQLite or filesystem details."""


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


def ddl_tokens(sql):
    """Ignore only ASCII whitespace between complete SQL lexical tokens.

    Preserve literal/quoted bytes, word case, comments, numeric spelling,
    constraints, operators and punctuation. Unknown syntax refuses the input.
    No schema supplied by the source is ever executed as a reference model.
    """
    if sql is None:
        return None
    if type(sql) is not str or len(sql) > 8192:
        raise Refused()
    result = []
    position = 0
    while position < len(sql):
        if sql[position] in ' \t\r\n\f\v':
            position += 1
            continue
        token = DDL_TOKEN.match(sql, position)
        if token is None:
            raise Refused()
        result.append((token.lastgroup, token.group()))
        position = token.end()
    return tuple(result)


def schema_objects(db):
    return [(kind, name, table, ddl_tokens(sql)) for kind, name, table, sql in objects(db)]


def reference(*, native=False, hashes=0, target=False, marker=None):
    db = connection()
    if target:
        db.executescript(schema('target-mail.sql'))
    else:
        if type(hashes) is not int or hashes not in (0, 1, 2):
            db.close()
            raise Refused()
        db.executescript(schema('native-mail.sql' if native else 'legacy-mail.sql'))
        if hashes >= 1:
            db.execute('ALTER TABLE courriels ADD COLUMN empreinte TEXT')
        if hashes == 2:
            db.execute('ALTER TABLE courriels ADD COLUMN empreinte_metier TEXT')
    if marker is not None:
        if marker not in MARKERS:
            db.close()
            raise Refused()
        db.executescript(schema(MARKERS[marker][2]))
    return db


def inspect(raw, *, target=False, scope='mail'):
    if scope not in ('mail', 'cycle', 'closure', 'global', 'archive'):
        raise Refused()
    if not target and len(raw) > MAX_SOURCE:
        raise Refused()
    db = connection(raw)
    try:
        permitted = []
        versions = [(False, 0)] if target else [(native, hashes) for native in (False, True) for hashes in (0, 1, 2)]
        for native, hashes in versions:
            for marker in ((None, scope) if scope in MARKERS else (None,)):
                model = reference(native=native, hashes=hashes, target=target, marker=marker)
                try:
                    permitted.append(schema_objects(model))
                finally:
                    model.close()
        if schema_objects(db) not in permitted or db.execute('PRAGMA integrity_check(1)').fetchone() != ('ok',):
            raise Refused()
        return db
    except Exception:
        db.close()
        raise


def rows(db):
    values = db.execute('SELECT * FROM courriels ORDER BY cle COLLATE BINARY LIMIT 10001').fetchall()
    if len(values) > MAX_ROWS:
        raise Refused()
    columns = db.execute('PRAGMA table_info(courriels)').fetchall()
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


def canonical_row(names, row):
    p = dict(zip(names, row, strict=True))
    # The historical queue accepts these keys without a prefix restriction.
    if not isinstance(p['cle'], str) or not KEY.fullmatch(p['cle']):
        raise Refused()
    if p['etat'] not in ('attente', 'accepte_relais', 'annule') or len(p['message']) > 131072:
        raise Refused()
    if any(type(p[name]) is not int or p[name] < 0 for name in ('cree', 'essais', 'prochain')):
        raise Refused()
    if p['accepte'] is not None and (type(p['accepte']) is not int or p['accepte'] < 0):
        raise Refused()
    digest = p.get('empreinte')
    if digest is not None and (not HASH.fullmatch(digest) or (p['message'] and hashlib.sha256(p['message']).hexdigest() != digest)):
        raise Refused()
    business_hash = p.get('empreinte_metier')
    if business_hash is not None and not HASH.fullmatch(business_hash):
        raise Refused()
    # Lisp's JSON-array digest is not Rust's JSON-object digest. An absent
    # historical proof remains NULL. Neither MIME nor a proof is regenerated.
    return tuple(p[name] for name in ('cle', 'message', 'cree', 'etat', 'essais', 'prochain', 'accepte', 'erreur')) + (digest, None, business_hash)


def marker_rows(db, scope):
    if scope not in MARKERS:
        return None
    table, key, _ = MARKERS[scope]
    if not db.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?', ('table', table)).fetchone():
        return None
    values = db.execute(f'SELECT * FROM {table} ORDER BY {key} COLLATE BINARY LIMIT 10001').fetchall()
    if len(values) > MAX_ROWS:
        raise Refused()
    for row in values:
        if not isinstance(row[0], str) or not IDENTIFIER.fullmatch(row[0]):
            raise Refused()
        if any(value is not None and (type(value) is not int or value < 0) for value in row[1:]):
            raise Refused()
    return values


def merge(*snapshots, profile=None):
    if len(snapshots) not in (1, 2):
        raise Refused()
    if profile not in (None, 'cycle', 'archive'):
        raise Refused()
    if (profile == 'cycle' and len(snapshots) != 1) or (profile == 'archive' and len(snapshots) != 2):
        raise Refused()
    scopes = ('cycle',) if profile == 'cycle' else ('closure', 'global') if profile == 'archive' else ('mail',) * len(snapshots)
    copied = {}
    markers = None
    for raw, scope in zip(snapshots, scopes, strict=True):
        db = inspect(raw, scope=scope)
        try:
            if scope in MARKERS:
                markers = marker_rows(db, scope)
            names, values = rows(db)
            for row in values:
                canonical = canonical_row(names, row)
                key = canonical[0]
                # A shared key denotes the same idempotent queue operation.
                # Deduplicate only when every preserved value is identical.
                # Even different retry metadata or absent proofs conflict.
                if key in copied and copied[key] != canonical:
                    raise Refused()
                copied[key] = canonical
                if len(copied) > MAX_ROWS:
                    raise Refused()
        finally:
            db.close()
    destination = reference(target=True, marker=profile if markers is not None else None)
    try:
        with destination:
            destination.executemany('INSERT INTO courriels VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                                    (copied[key] for key in sorted(copied)))
            if markers is not None:
                table = MARKERS[profile][0]
                parameters = '?' if profile == 'cycle' else '?,?,?'
                destination.executemany(f'INSERT INTO {table} VALUES({parameters})', markers)
        result = destination.serialize()
        if len(result) > MAX_TARGET:
            raise Refused()
        return result
    finally:
        destination.close()


def equivalent(left, right):
    scope = PROFILE if PROFILE in PROFILES else 'mail'
    a = inspect(left, target=True, scope=scope)
    b = None
    try:
        b = inspect(right, target=True, scope=scope)
        return rows(a) == rows(b) and marker_rows(a, scope) == marker_rows(b, scope)
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


def profile():
    if PROFILE not in PROFILES:
        raise Refused()
    return PROFILES[PROFILE]


def sealed_input(name):
    input_directory, names, _ = profile()
    if name not in names:
        raise Refused()
    parent = os.open(input_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
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
        _, names, state = profile()
        os.umask(0o077)
        result = merge(*(sealed_input(name) for name in names), profile=PROFILE)
        publish(state, result)
        print('{"status":"adopted"}')
    except Exception:
        print('{"error":"MAIL_ADOPTION_REFUSED"}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
