"""Sealed code import after release005; no unit, profile or service mutation."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import selectors
import signal
import stat
import subprocess
import sys
import time

RELEASE = {'schema_version': 1, 'export_sha256': '432595565617c33f930c54c127f0a88ac1112af9dd5b4a18b61caae3d9ca67f7', 'export_bytes': 1331224, 'required_free_bytes': 1076404272, 'artifacts': {'/nix/store/5mljdc68ab1siz9w0ckwmnjfn6969hqa-mrjam-validation-authority-key-bootstrap-1': {'nar_hash': 'sha256-pGx2E15GblvB3xqfrTe5QZvcRJoYxamFT53Hk4Bf8rI=', 'references': ['/nix/store/5mljdc68ab1siz9w0ckwmnjfn6969hqa-mrjam-validation-authority-key-bootstrap-1', '/nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin', '/nix/store/hc49zakwkkyp9zlyl80b71jhxkpn4hsx-bash-5.3p9', '/nix/store/kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-python3-3.13.17']}, '/nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin': {'nar_hash': 'sha256-i89zhk1jawVLvmwERelB7ipz1St+Lg7Yg+c2crjRrBE=', 'references': ['/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103', '/nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin', '/nix/store/q1fgk31hkgl8a7znhmvb0bq8bbcaf64y-openssl-3.6.5']}}}
CURRENT = '/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git'
DIRECTORY = Path('/var/lib/mrjam-deployment-delivery/ci-key-bootstrap-20261103')
STATE = Path('/var/lib/mrjam-cutover/first-deployment')
RESULT_DIRECTORY = Path('/run/mrjam-first-release-status-05')
STORE = re.compile(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._?=-]{1,200}\Z')
NAR = re.compile(r'sha256-[A-Za-z0-9+/]{43}=\Z')


class Refused(RuntimeError):
    pass


def require(value):
    if not value:
        raise Refused('POSTRELEASE_CODE_IMPORT_REFUSED')


def parse(raw):
    def unique(items):
        value = {}
        for key, item in items:
            require(key not in value)
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


def validate_release(value):
    require(type(value) is dict and set(value) == {
        'schema_version', 'export_sha256', 'export_bytes', 'required_free_bytes', 'artifacts'})
    require(type(value['schema_version']) is int and value['schema_version'] == 1)
    require(type(value['export_sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['export_sha256']))
    require(type(value['export_bytes']) is int and 0 < value['export_bytes'] <= 1024**3)
    require(type(value['required_free_bytes']) is int
            and 2 * value['export_bytes'] + 1024**3 <= value['required_free_bytes'] <= 8 * 1024**3)
    artifacts = value['artifacts']
    require(type(artifacts) is dict and 0 < len(artifacts) <= 10000)
    for path, info in artifacts.items():
        require(type(path) is str and STORE.fullmatch(path))
        require(type(info) is dict and set(info) == {'nar_hash', 'references'})
        require(type(info['nar_hash']) is str and NAR.fullmatch(info['nar_hash']))
        refs = info['references']
        require(type(refs) is list and len(refs) <= 4096 and refs == sorted(set(refs)))
        require(all(type(item) is str and STORE.fullmatch(item) for item in refs))
    return value


def protected_directory(path, create=False):
    """No symlink traversal and no writable ancestor outside root."""
    descriptor=os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        for part in Path(path).parts[1:]:
            if create:
                try:
                    os.mkdir(part,0o700,dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=descriptor)
            os.close(descriptor);descriptor=child
            item=os.fstat(descriptor)
            require(item.st_uid==0 and not stat.S_IMODE(item.st_mode)&0o022)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def receive(stream, directory, release):
    # Only this fixed, bound public code archive can be replaced on retry.
    fd=os.open("export.partial",os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
    try:
        item=os.fstat(fd)
        require(stat.S_ISREG(item.st_mode) and item.st_uid==os.geteuid() and item.st_nlink==1
                and stat.S_IMODE(item.st_mode)==0o600)
        os.ftruncate(fd,0)
        digest=hashlib.sha256();total=0
        with os.fdopen(fd,"wb",closefd=False) as output:
            while total<=release["export_bytes"]:
                block=stream.read(min(1024*1024,release["export_bytes"]-total+1))
                if not block:
                    break
                total+=len(block)
                require(total<=release["export_bytes"])
                digest.update(block);output.write(block)
            require(total==release["export_bytes"] and digest.hexdigest()==release["export_sha256"])
            output.flush();os.fsync(fd)
        os.rename("export.partial","export.nar",src_dir_fd=directory,dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        os.close(fd)


def private_json(directory, name, maximum):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, 'rb') as stream:
        item = os.fstat(stream.fileno())
        require(stat.S_ISREG(item.st_mode) and item.st_uid == item.st_gid == 0
                and item.st_nlink == 1 and stat.S_IMODE(item.st_mode) == 0o600)
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum)
    return parse(raw)


def gate(state):
    require(all(os.path.realpath(path) == CURRENT for path in ('/run/current-system', '/nix/var/nix/profiles/system')))
    phase = private_json(state, 'phase.json', 1024)
    require(type(phase) is dict and set(phase) == {'schema_version', 'phase', 'elapsed_seconds'}
            and type(phase['schema_version']) is int and phase['schema_version'] == 1
            and phase['phase'] == 'public-writes-open' and type(phase['elapsed_seconds']) is int
            and phase['elapsed_seconds'] >= 0)
    result_directory = protected_directory(RESULT_DIRECTORY)
    try:
        result = private_json(result_directory, 'result.json', 1024)
        require(type(result) is dict and type(result.get('schema_version')) is int
                and result == {'schema_version': 1, 'code': 'CUTOVER_VERIFIED', 'phase': 'public-writes-open'})
    finally:
        os.close(result_directory)


def command(args, source=None):
    process = None
    try:
        process = subprocess.Popen(args, stdin=source if source is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
            env={'LANG': 'C', 'LC_ALL': 'C', 'NIX_PATH': ''})
        data = bytearray()
        end = time.monotonic() + 240
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = end - time.monotonic()
                require(remaining > 0 and selector.select(remaining))
                chunk = os.read(process.stdout.fileno(), 16384)
                if not chunk:
                    break
                data.extend(chunk)
                require(len(data) <= 2 * 1024**2)
        require(process.wait(timeout=max(.01, end - time.monotonic())) == 0)
        return bytes(data)
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=1)
            process.stdout.close()


def verify_import(release, imported):
    observed = imported.decode('ascii').splitlines()
    paths = sorted(release['artifacts'])
    require(len(observed) == len(set(observed)) and set(observed) == set(paths))
    command([CURRENT + '/sw/bin/nix-store', '--verify-path', *paths])
    info = parse(command([CURRENT + '/sw/bin/nix', '--extra-experimental-features', 'nix-command',
                          'path-info', '--json', *paths]))
    if type(info) is list:
        require(all(type(item) is dict and type(item.get('path')) is str for item in info))
        require(len({item['path'] for item in info}) == len(info))
        info = {item['path']: item for item in info}
    require(type(info) is dict and set(info) == set(paths))
    for path in paths:
        require(type(info[path]) is dict and info[path].get('narHash') == release['artifacts'][path]['nar_hash']
                and sorted(info[path].get('references', [])) == release['artifacts'][path]['references'])


def deliver(release, stream):
    release = validate_release(release)
    require(os.geteuid() == os.getegid() == 0 and os.uname().nodename == 'srv1982677')
    state = protected_directory(STATE)
    lock = work = None
    try:
        lock = os.open('transaction.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=state)
        item = os.fstat(lock)
        require(stat.S_ISREG(item.st_mode) and item.st_uid == item.st_gid == 0
                and item.st_nlink == 1 and stat.S_IMODE(item.st_mode) == 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gate(state)
        work = protected_directory(DIRECTORY, create=True)
        require(stat.S_IMODE(os.fstat(work).st_mode) == 0o700)
        fcntl.flock(work, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for filesystem in (os.fstatvfs(work), os.statvfs('/nix/store')):
            require(filesystem.f_bavail * filesystem.f_frsize >= release['required_free_bytes'])
        binding = (json.dumps(release, sort_keys=True, separators=(',', ':')) + '\n').encode()
        try:
            fd = os.open('release.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=work)
        except FileExistsError:
            require(private_json(work, 'release.json', 2 * 1024**2) == release)
        else:
            with os.fdopen(fd, 'wb') as output:
                output.write(binding)
                output.flush()
                os.fsync(output.fileno())
            os.fsync(work)
        receive(stream, work, release)
        gate(state)
        fd = os.open('export.nar', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=work)
        with os.fdopen(fd, 'rb') as archive:
            imported = command([CURRENT + '/sw/bin/nix-store', '--import'], source=archive)
        verify_import(release, imported)
        gate(state)
    finally:
        if work is not None:
            os.close(work)
        if lock is not None:
            os.close(lock)
        os.close(state)
    return {'schema_version': 1, 'code': 'POSTRELEASE_CODE_IMPORTED', 'store_paths': len(release['artifacts']),
            'application_activation': False, 'systemd_changes': False}


def main():
    try:
        require(len(sys.argv) == 1)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.umask(0o077)
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(Refused()))
        signal.alarm(600)
        value = deliver(RELEASE, sys.stdin.buffer)
    except Exception:
        print('{"schema_version":1,"code":"POSTRELEASE_CODE_IMPORT_REFUSED"}')
        return 1
    finally:
        signal.alarm(0)
    print(json.dumps(value, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
