"""One human-root bootstrap operation. No arguments or remotely selectable action."""
import json
import fcntl
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).absolute().parent
sys.path.insert(0, str(ROOT))
from bounded import Refused, run

UNIT = "mrjam-observe-adoption"
ENVIRONMENT = {
    "LANG": "C", "LC_ALL": "C", "PATH": "/no-path",
    "DBUS_SYSTEM_BUS_ADDRESS": "unix:path=/run/dbus/system_bus_socket",
    "SYSTEMD_LOG_LEVEL": "emerg", "SYSTEMD_COLORS": "0",
}
PROPERTIES = (
    "User=mrjam-inventory", "Group=mrjam-inventory", "DynamicUser=no",
    "WorkingDirectory=/", "UMask=0077", "StandardError=null",
    "PrivateNetwork=yes", "IPAddressDeny=any", "RestrictAddressFamilies=AF_UNIX",
    "NoNewPrivileges=yes", "CapabilityBoundingSet=", "AmbientCapabilities=",
    "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "PrivateDevices=yes",
    "PrivateIPC=yes", "ProtectKernelTunables=yes", "ProtectKernelModules=yes",
    "ProtectKernelLogs=yes", "ProtectControlGroups=yes", "ProtectClock=yes",
    "RestrictSUIDSGID=yes", "RestrictRealtime=yes", "RestrictNamespaces=yes",
    "LockPersonality=yes", "MemoryDenyWriteExecute=yes", "ProtectProc=invisible",
    "ProcSubset=pid", "SystemCallArchitectures=native", "SystemCallFilter=@system-service",
    "CPUAccounting=yes", "CPUQuota=20%", "MemoryAccounting=yes", "MemoryMax=192M",
    "TasksAccounting=yes", "TasksMax=12", "LimitNOFILE=64", "LimitCORE=0",
    "TimeoutStartSec=20s", "RuntimeMaxSec=60s", "TimeoutStopSec=2s",
    "KillMode=control-group", "SendSIGKILL=yes",
    "InaccessiblePaths=-/etc/shadow -/etc/gshadow -/run/secrets -/var/lib/postgresql "
    "-/var/lib/forgejo -/var/lib/gitea -/var/lib/kanidm -/var/lib/nextcloud "
    "-/var/lib/private -/var/backups -/var/backup -/run/docker.sock "
    "-/run/podman -/run/libvirt -/run/sssd -/var/lib/sss -/run/nslcd -/run/nscd/socket",
)


def command(runtime):
    return [runtime["systemd_run"], "--system", "--quiet", "--pipe", "--wait", "--collect",
            "--service-type=exec", "--unit=" + UNIT,
            *["--property=" + value for value in PROPERTIES],
            "--", runtime["python"], "-I", "-S", str(ROOT / "collect.py")]


def immutable_entry():
    if not re.fullmatch(r"/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-mrjam-observe-adoption-v2/libexec", str(ROOT)):
        raise Refused()
    for path in (ROOT, ROOT / "observe.py", ROOT / "bounded.py", ROOT / "runtime.json"):
        value = path.lstat()
        if stat.S_ISLNK(value.st_mode) or value.st_uid != 0 or value.st_mode & 0o022:
            raise Refused()
    manager = Path("/run/systemd/system").lstat()
    if not stat.S_ISDIR(manager.st_mode) or manager.st_uid != 0 or manager.st_mode & 0o022:
        raise Refused()


def acquire_lock():
    parent = Path("/run").lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022:
        raise Refused()
    descriptor = os.open("/run/mrjam-observe-adoption.lock",
                         os.O_RDONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600)
    try:
        value = os.fstat(descriptor)
        if (not stat.S_ISREG(value.st_mode) or value.st_uid != 0 or value.st_gid != 0
                or stat.S_IMODE(value.st_mode) != 0o600 or value.st_nlink != 1 or value.st_size != 0):
            raise Refused()
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise Refused() from None


def main():
    lock = None
    try:
        if len(sys.argv) != 1 or os.getuid() != 0 or os.geteuid() != 0:
            raise Refused()
        immutable_entry()
        lock = acquire_lock()
        runtime = json.loads((ROOT / "runtime.json").read_text())
        state = run([runtime["systemctl"], "--system", "show", "--property=LoadState",
                     "--value", UNIT + ".service"], environment=ENVIRONMENT,
                    seconds=10, limit=32)
        if state != b"not-found\n":
            raise Refused()
        # Enclose setup (20), runtime (60), stop (2), and client overhead.
        # CPU throttling and TCG qualification must not invalidate this sum.
        report = run(command(runtime), environment=ENVIRONMENT, seconds=90)
        # Validate again before the sole external output. A rejected service,
        # output flood, timeout or malformed document yields no stdout.
        filtered = run([runtime["python"], "-I", "-S", str(ROOT / "probe/validate_report.py")],
                       environment={"LANG": "C", "LC_ALL": "C", "PATH": "/no-path"},
                       seconds=15, input_bytes=report)
        sys.stdout.buffer.write(filtered)
        return 0
    except Exception:
        sys.stderr.write("OBSERVATION_FAILED\n")
        return 65
    finally:
        if lock is not None:
            os.close(lock)


if __name__ == "__main__":
    raise SystemExit(main())
