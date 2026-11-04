"""Start the single sealed deployment independently of the SSH connection."""
import json
import os
from pathlib import Path
import resource
import stat
import subprocess
import sys

CONTROLLER = "/nix/store/irb47r5zxmffhlklmf2c613gdm8ydb1z-mrjam-first-release-controller-1"
SYSTEMD = "/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/"
UNIT = "mrjam-first-release-20261102.service"
DIRECTORY = Path("/run/mrjam-first-release-status")


def main():
    try:
        assert len(sys.argv) == 1 and os.geteuid() == os.getegid() == 0
        assert os.uname().nodename == "srv1982677"
        os.umask(0o077)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        before = subprocess.run([SYSTEMD + "systemctl", "show", UNIT, "--property=LoadState", "--value"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=10, check=False)
        assert before.returncode == 0 and before.stdout == b"not-found\n"
        root = Path("/run").lstat()
        assert stat.S_ISDIR(root.st_mode) and root.st_uid == 0 and not root.st_mode & 0o022
        DIRECTORY.mkdir(mode=0o700)
        item = DIRECTORY.lstat()
        assert stat.S_ISDIR(item.st_mode) and item.st_uid == item.st_gid == 0
        assert stat.S_IMODE(item.st_mode) == 0o700
        result = DIRECTORY / "result.json"
        fd = os.open(result, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        os.fsync(fd)
        os.close(fd)
        properties = (
            "User=root", "Group=root", "UMask=0077", "WorkingDirectory=/",
            "StandardInput=null", "StandardError=null", "StandardOutput=append:" + str(result),
            "Restart=no", "KillMode=mixed", "KillSignal=SIGTERM", "SendSIGHUP=no", "SendSIGKILL=no",
            "TimeoutStartSec=30s", "TimeoutStopSec=infinity", "RuntimeMaxSec=infinity", "LimitCORE=0",
        )
        command = [SYSTEMD + "systemd-run", "--system", "--unit=" + UNIT, "--service-type=exec",
                   "--remain-after-exit", "--expand-environment=no"]
        command += ["--property=" + value for value in properties]
        command += ["--", CONTROLLER + "/bin/mrjam-first-release-deploy"]
        started = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, timeout=40, check=False)
        assert started.returncode == 0
    except BaseException:
        print('{"schema_version":1,"code":"FIRST_RELEASE_LAUNCH_NOT_CONFIRMED"}')
        return 1
    print('{"schema_version":1,"code":"FIRST_RELEASE_PROCESS_STARTED","deployment_complete":false}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
