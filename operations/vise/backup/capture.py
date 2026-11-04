"""Private paired ViSe snapshot. No restore, export or caller-supplied SQL.

The caller must hold the deployment lock and keep ViSe stopped throughout.
Command paths come only from the immutable package. All subprocess diagnostics
are suppressed; the public result is a fixed code, never application data.
"""
import hashlib
import os
from pathlib import Path
import pwd
import resource
import stat
import subprocess


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def directory(path, owner, group=None):
    group = owner if group is None else group
    path = Path(path)
    require(path.is_absolute(), 'VISE_BACKUP_PATH_REFUSED')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        require(info.st_uid == owner and info.st_gid == group and stat.S_IMODE(info.st_mode) == 0o700,
                'VISE_BACKUP_DIRECTORY_REFUSED')
        return info
    finally:
        os.close(fd)


def regular(path, owner, maximum, group=None):
    group = owner if group is None else group
    directory(Path(path).parent, owner, group)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == owner and info.st_gid == group
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= maximum,
                'VISE_BACKUP_FILE_REFUSED')
        return fd, info
    except BaseException:
        os.close(fd)
        raise


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def hash_private(path, owner, maximum, group=None):
    fd, _ = regular(path, owner, maximum, group)
    with os.fdopen(fd, 'rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


class Snapshot:
    MAX_LEDGER = 64 * 1024**2
    MAX_DATABASE = 8 * 1024**3

    def __init__(self, tools, root, ledger='/var/lib/etp-carnet/deletions.log'):
        self.tools, self.root, self.ledger = tools, Path(root), Path(ledger)
        self.uid = pwd.getpwnam('etp_carnet').pw_uid
        self.postgres = pwd.getpwnam('postgres')

    def pg_identity(self):
        # Report only which fixed privilege/limit operation failed. Never
        # continue to PostgreSQL if dropping identity or applying limits fails.
        for code, operation in [
            (73, lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0))),
            (74, lambda: resource.setrlimit(resource.RLIMIT_FSIZE, (self.MAX_DATABASE, self.MAX_DATABASE))),
            (75, lambda: os.setgroups([])),
            (76, lambda: os.setgid(self.postgres.pw_gid)),
            (77, lambda: os.setuid(self.postgres.pw_uid)),
        ]:
            try: operation()
            except Exception: os._exit(code)

    def run(self, argv, *, output=None, postgres=False, timeout=30, capture=False):
        try:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE if capture else (output or subprocess.DEVNULL),
                stderr=subprocess.DEVNULL, timeout=timeout,
                preexec_fn=self.pg_identity if postgres else None,
                env={'LC_ALL': 'C', 'PGCONNECT_TIMEOUT': '5'})
        except (OSError, subprocess.TimeoutExpired):
            raise Refused('VISE_BACKUP_COMMAND_REFUSED') from None
        child_codes = {73: 'VISE_BACKUP_CORE_LIMIT_REFUSED', 74: 'VISE_BACKUP_FILE_LIMIT_REFUSED',
            75: 'VISE_BACKUP_GROUPS_DROP_REFUSED', 76: 'VISE_BACKUP_GID_DROP_REFUSED', 77: 'VISE_BACKUP_UID_DROP_REFUSED'}
        require(result.returncode == 0, child_codes.get(result.returncode, 'VISE_BACKUP_COMMAND_REFUSED')
                if postgres else 'VISE_BACKUP_COMMAND_REFUSED')
        return result.stdout if capture else None

    def sql_number(self, statement):
        # Call sites below contain the only permitted statements. No CLI input
        # or backup contents are ever used as SQL.
        raw = self.run([self.tools['psql'], '-XwqAt', '-h', '/run/postgresql',
            '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', statement],
            postgres=True, capture=True)
        require(len(raw) <= 32 and raw.strip().isdigit(), 'VISE_BACKUP_SQL_METADATA_REFUSED')
        return int(raw)

    def offline(self):
        raw = self.run([self.tools['systemctl'], 'show', 'vise.service',
                        '-p', 'ActiveState', '--value'], capture=True)
        require(raw.strip() == b'inactive', 'VISE_BACKUP_WRITER_ACTIVE')
        require(self.sql_number("SELECT count(*) FROM pg_stat_activity WHERE datname='etp_carnet'") == 0,
                'VISE_BACKUP_SQL_CONNECTION_PRESENT')
        for process in Path('/proc').iterdir():
            if process.name.isdigit():
                try:
                    require(process.stat().st_uid != self.uid, 'VISE_BACKUP_PROCESS_PRESENT')
                except FileNotFoundError:
                    pass

    def preflight(self):
        directory(self.root, 0)
        fd, info = regular(self.ledger, self.uid, self.MAX_LEDGER)
        os.close(fd)
        size = self.sql_number("SELECT pg_database_size('etp_carnet')")
        require(size <= self.MAX_DATABASE, 'VISE_BACKUP_DATABASE_LIMIT')
        space = os.statvfs(self.root)
        require(space.f_bavail * space.f_frsize > size * 5 + info.st_size * 5 + 2 * 1024**3,
                'VISE_BACKUP_FREE_SPACE_REFUSED')

    def capture(self, path):
        self.offline()
        directory(path, 0)
        require(not list(Path(path).iterdir()), 'VISE_BACKUP_DESTINATION_NOT_EMPTY')
        fd, before = regular(self.ledger, self.uid, self.MAX_LEDGER)
        try:
            with (Path(path) / 'database.dump').open('xb') as output:
                os.fchmod(output.fileno(), 0o600)
                self.run([self.tools['pg_dump'], '-h', '/run/postgresql', '-w', '-Fc',
                          '--no-owner', '--no-privileges', 'etp_carnet'],
                         output=output, postgres=True, timeout=180)
                output.flush()
                require(os.fstat(output.fileno()).st_size <= self.MAX_DATABASE,
                        'VISE_BACKUP_DUMP_LIMIT')
                os.fsync(output.fileno())
            with os.fdopen(fd, 'rb', closefd=False) as source, (Path(path) / 'deletions.log').open('xb') as output:
                os.fchmod(output.fileno(), 0o600)
                size = 0
                while block := source.read(65536):
                    size += len(block)
                    require(size <= self.MAX_LEDGER, 'VISE_BACKUP_LEDGER_LIMIT')
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
                require(size == before.st_size and fingerprint(os.fstat(fd)) == fingerprint(before),
                        'VISE_BACKUP_LEDGER_CHANGED')
        finally:
            os.close(fd)
        self.offline()
        current, after = regular(self.ledger, self.uid, self.MAX_LEDGER)
        os.close(current)
        require(fingerprint(before) == fingerprint(after), 'VISE_BACKUP_LEDGER_CHANGED')
        require(hash_private(self.ledger, self.uid, self.MAX_LEDGER)
                == hash_private(Path(path) / 'deletions.log', 0, self.MAX_LEDGER),
                'VISE_BACKUP_LEDGER_CHANGED')
        self.verify(path)
        sync(path)

    def verify(self, path):
        directory(path, 0)
        require({p.name for p in Path(path).iterdir()} == {'database.dump', 'deletions.log'},
                'VISE_BACKUP_COMPONENTS_REFUSED')
        for name, maximum in [('database.dump', self.MAX_DATABASE), ('deletions.log', self.MAX_LEDGER)]:
            fd, info = regular(Path(path) / name, 0, maximum)
            os.close(fd)
            require(name != 'database.dump' or info.st_size > 0, 'VISE_BACKUP_DUMP_EMPTY')
        self.run([self.tools['pg_restore'], '--list', str(Path(path) / 'database.dump')])
