#!/usr/bin/env python3
"""One proposed, nonprivileged observation; distinct from inventory V1.

No arguments, shell, external executable, network API, secret/key read or mutation.
Only fixed metadata is observed; the supervisor forks one local Python child.
NSS lookups are for one fixed account only. Their system backend is not controlled
by this code; an independently authorized operator must decide its isolation.
"""
import errno
import grp
import json
import os
import pwd
import re
import resource
import select
import signal
import stat
import sys
import time

ACCOUNT = "mrjam-inventory"
ROOT = "/var/lib/mrjam-inventory-access"
MAX_ID = 2**31 - 1
MAX_GROUPS = 256
MAX_OUTPUT = 8192
MAX_SECONDS = 5
STORE = re.compile(r"/nix/store/([0-9abcdfghijklmnpqrsvwxyz]{32})-[A-Za-z0-9+._?=\-]{1,211}")
PROFILE = re.compile(r"(?:/nix/var/nix/profiles/)?system-([1-9][0-9]{0,9})-link")
PATHS = {
    "base": (ROOT, True, 0o755, False),
    "home": (ROOT + "/home", True, 0o755, False),
    "ssh_directory": (ROOT + "/home/.ssh", True, 0o755, False),
    "authorized_keys": (ROOT + "/home/.ssh/authorized_keys", False, 0o644, False),
    "login": (ROOT + "/login", False, 0o555, False),
    "runner": (ROOT + "/runner.py", False, 0o444, False),
    "work": (ROOT + "/work", True, 0o700, True),
    "declarative_authorized_keys": ("/etc/ssh/mrjam-inventory-authorized-keys", False, 0o444, False),
}


class Unavailable(Exception):
    def __init__(self, code):
        self.code = code


class Deadline(Exception):
    pass


class OutputLimit(Exception):
    pass


def _deadline(_signal, _frame):
    raise Deadline()


def _cap(which, limit):
    soft, hard = resource.getrlimit(which)
    limit = min([limit] + [v for v in (soft, hard) if v != resource.RLIM_INFINITY])
    resource.setrlimit(which, (limit, limit))


def constrain():
    signal.signal(signal.SIGALRM, _deadline)
    signal.setitimer(signal.ITIMER_REAL, MAX_SECONDS)
    _cap(resource.RLIMIT_CORE, 0)
    _cap(resource.RLIMIT_CPU, 2)
    _cap(resource.RLIMIT_AS, 128 * 1024 * 1024)
    _cap(resource.RLIMIT_NOFILE, 64)


def _positive(value):
    return type(value) is int and 1 <= value <= MAX_ID


def observe_account():
    unknown = {"state": "unknown", "code": "UNAVAILABLE", "uid": None, "gid": None,
               "home_matches": None, "shell_matches": None, "group_matches": None,
               "supplementary_groups_absent": None}
    try:
        user = pwd.getpwnam(ACCOUNT)
    except KeyError:
        return dict(unknown, state="absent", code="NOT_FOUND")
    except (OSError, ValueError, OverflowError):
        return unknown
    if not _positive(user.pw_uid) or not _positive(user.pw_gid):
        return dict(unknown, code="INVALID_OUTPUT")
    result = dict(unknown, state="observed", code="OK", uid=user.pw_uid, gid=user.pw_gid,
                  home_matches=user.pw_dir == ROOT + "/home",
                  shell_matches=user.pw_shell == ROOT + "/login")
    try:
        group = grp.getgrnam(ACCOUNT)
        result["group_matches"] = group.gr_gid == user.pw_gid if _positive(group.gr_gid) else None
    except KeyError:
        result["group_matches"] = False
    except (OSError, ValueError, OverflowError):
        pass
    try:
        groups = os.getgrouplist(ACCOUNT, user.pw_gid)
        if (type(groups) is list and 1 <= len(groups) <= MAX_GROUPS
                and all(_positive(value) for value in groups)):
            result["supplementary_groups_absent"] = set(groups) == {user.pw_gid}
    except (OSError, ValueError, OverflowError):
        pass
    return result


def _root_directory(value):
    return (stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and value.st_gid == 0
            and not stat.S_IMODE(value.st_mode) & 0o022)


def _error(error):
    if error.errno == errno.ENOENT:
        return "NOT_FOUND"
    if error.errno in (errno.ELOOP, errno.ENOTDIR):
        return "PARENT_UNSAFE"
    return "UNAVAILABLE"


def _parent_fd(path):
    """Open only root-owned fixed parents, without following any symlink.

    Paths originate solely in PATHS/current/profile constants, never arguments,
    the environment or the target text of a symlink.
    """
    descriptor = None
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptor = os.open("/", flags)
        if not _root_directory(os.fstat(descriptor)):
            raise Unavailable("PARENT_UNSAFE")
        for part in path.split("/")[1:-1]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            if not _root_directory(os.fstat(descriptor)):
                raise Unavailable("PARENT_UNSAFE")
        return descriptor
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise Unavailable(_error(error)) from None
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        raise


def safe_lstat(path):
    descriptor = _parent_fd(path)
    try:
        return os.stat(path.rsplit("/", 1)[1], dir_fd=descriptor, follow_symlinks=False)
    except OSError as error:
        raise Unavailable(_error(error)) from None
    finally:
        os.close(descriptor)


def _identity(value):
    return (value.st_dev, value.st_ino, value.st_uid, value.st_gid,
            value.st_mode, value.st_mtime_ns, value.st_ctime_ns)


def safe_readlink(path):
    descriptor = _parent_fd(path)
    try:
        name = path.rsplit("/", 1)[1]
        before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if not stat.S_ISLNK(before.st_mode) or before.st_uid != 0 or before.st_gid != 0:
            raise Unavailable("INVALID_OUTPUT")
        target = os.readlink(name, dir_fd=descriptor)
        after = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if _identity(before) != _identity(after):
            raise Unavailable("CHANGED")
        if len(target) > 4096:
            raise Unavailable("INVALID_OUTPUT")
        return target
    except OSError as error:
        raise Unavailable(_error(error)) from None
    finally:
        os.close(descriptor)


def _failed(code, **values):
    return dict(values, state="absent" if code == "NOT_FOUND" else "unknown", code=code)


def observe_paths(account):
    result = {}
    for label, (path, directory, mode, account_owned) in PATHS.items():
        try:
            value = safe_lstat(path)
            uid, gid = (account["uid"], account["gid"]) if account_owned else (0, 0)
            result[label] = {
                "state": "observed", "code": "OK",
                "type_matches": (stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode)),
                "owner_matches": None if uid is None else value.st_uid == uid,
                "group_matches": None if gid is None else value.st_gid == gid,
                "mode_matches": stat.S_IMODE(value.st_mode) == mode,
            }
        except Unavailable as error:
            result[label] = _failed(error.code, type_matches=None, owner_matches=None,
                                    group_matches=None, mode_matches=None)
    return result


def _store_hash(path):
    match = STORE.fullmatch(safe_readlink(path))
    if match is None:
        raise Unavailable("INVALID_OUTPUT")
    return match.group(1)


def observe_generation():
    try:
        current = {"state": "observed", "code": "OK", "store_hash": _store_hash("/run/current-system")}
    except Unavailable as error:
        current = _failed(error.code, store_hash=None)
    try:
        target = safe_readlink("/nix/var/nix/profiles/system")
        match = PROFILE.fullmatch(target)
        if match is None or not 1 <= int(match.group(1)) <= MAX_ID:
            raise Unavailable("INVALID_OUTPUT")
        number = int(match.group(1))
        store_hash = _store_hash("/nix/var/nix/profiles/system-" + str(number) + "-link")
        # Check the profile pointer again so a concurrent profile update is not
        # reported as one consistent observation. A global snapshot is not claimed.
        if safe_readlink("/nix/var/nix/profiles/system") != target:
            raise Unavailable("CHANGED")
        profile = {"state": "observed", "code": "OK", "number": number, "store_hash": store_hash,
                   "matches_current": None if current["store_hash"] is None else store_hash == current["store_hash"]}
    except Unavailable as error:
        profile = _failed(error.code, number=None, store_hash=None, matches_current=None)
    return {"current": current, "profile": profile}


def collect():
    account = observe_account()
    return {"schema_version": 1, "operation": "mrjam-inventory-adoption-v2",
            "authority": "unverified_observation", "account": account,
            "paths": observe_paths(account), "generation": observe_generation()}


def bounded_collect():
    """A local fork, never a command/executable chosen by the caller.

    The parent owns the deadline, so a blocking libc NSS call cannot postpone
    it. Only a complete successful child result can reach the output filter.
    """
    reader, writer = os.pipe()
    try:
        child = os.fork()
    except BaseException:
        os.close(reader)
        os.close(writer)
        raise
    if child == 0:
        os.close(reader)
        status = 70
        try:
            output = json.dumps(collect(), separators=(",", ":"), sort_keys=True).encode("ascii")
            if len(output) + 1 > MAX_OUTPUT:
                status = 65
            else:
                view = memoryview(output)
                while view:
                    count = os.write(writer, view)
                    view = view[count:]
                status = 0
        except BaseException:
            pass
        finally:
            os.close(writer)
            os._exit(status)
    os.close(writer)
    received = bytearray()
    deadline = time.monotonic() + MAX_SECONDS
    reaped, ended, status = False, False, None
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Deadline()
            if not ended:
                ready, _, _ = select.select([reader], [], [], min(remaining, 0.02))
                if ready:
                    chunk = os.read(reader, MAX_OUTPUT + 1 - len(received))
                    ended = not chunk
                    received.extend(chunk)
                    if len(received) + 1 > MAX_OUTPUT:
                        raise OutputLimit()
            else:
                select.select([], [], [], min(remaining, 0.005))
            if not reaped:
                found, exit_status = os.waitpid(child, os.WNOHANG)
                if found:
                    reaped, status = True, exit_status
            if reaped and ended:
                if os.WIFEXITED(status) and os.WEXITSTATUS(status) == 65:
                    raise OutputLimit()
                if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
                    raise RuntimeError()
                return received.decode("ascii")
    finally:
        os.close(reader)
        if not reaped:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
            # Do not replace the deadline with an unbounded wait on the kernel.
            reap_deadline = time.monotonic() + 0.1
            while time.monotonic() < reap_deadline:
                found, _ = os.waitpid(child, os.WNOHANG)
                if found:
                    break
                select.select([], [], [], 0.005)


def _refused(code, exit_code):
    print(json.dumps({"status": "refused", "code": code}, separators=(",", ":")))
    return exit_code


def main():
    if len(sys.argv) != 1:
        return _refused("UNSUPPORTED_ARGUMENTS", 64)
    if os.getuid() == 0 or os.geteuid() == 0:
        return _refused("PRIVILEGED_EXECUTION", 64)
    try:
        constrain()
        output = bounded_collect()
        print(output)
        return 0
    except Deadline:
        return _refused("DEADLINE_EXCEEDED", 75)
    except OutputLimit:
        return _refused("OUTPUT_LIMIT", 65)
    except Exception:
        return _refused("OBSERVATION_FAILED", 70)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    raise SystemExit(main())
