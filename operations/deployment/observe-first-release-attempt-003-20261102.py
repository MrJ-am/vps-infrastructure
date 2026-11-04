"""Read only closed lifecycle metadata for the fixed first deployment."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

CONTROLLER = "/nix/store/lviggl0pqmarmmhs8brqs4d34fa1cph3-mrjam-first-release-controller-1"
SYSTEMCTL = "/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl"
UNIT = "mrjam-first-release-20261102-03.service"


def main():
    try:
        assert len(sys.argv) == 1 and os.geteuid() == 0 and os.uname().nodename == "srv1982677"
        sys.path.insert(0, CONTROLLER + "/libexec")
        # Importing the immutable entrypoint never invokes its main().
        import deploy
        SAFE_FAILURES = deploy.SAFE_FAILURES
        from cutover import Phase, Checkpoint
        fields = ("LoadState", "ActiveState", "SubState", "Result", "MainPID", "ExecMainCode", "ExecMainStatus")
        observed = subprocess.run([SYSTEMCTL, "show", UNIT, *["--property=" + x for x in fields]],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  timeout=10, check=False)
        assert observed.returncode == 0 and len(observed.stdout) <= 4096
        pairs = [line.split("=", 1) for line in observed.stdout.decode("ascii").splitlines()]
        value = dict(pairs)
        assert len(pairs) == len(fields) and set(value) == set(fields)
        assert value["LoadState"] in ("loaded", "not-found", "error", "masked", "bad-setting")
        assert value["ActiveState"] in ("active", "inactive", "activating", "deactivating", "failed")
        assert value["SubState"] in ("running", "exited", "dead", "failed", "start", "start-pre", "stop", "stop-sigterm", "stop-sigkill", "final-sigterm")
        assert value["Result"] in ("success", "exit-code", "signal", "timeout", "core-dump", "resources", "protocol", "start-limit-hit", "")
        for field in ("MainPID", "ExecMainCode", "ExecMainStatus"):
            assert value[field].isdigit()
            value[field] = int(value[field])
        result = None
        path = Path("/run/mrjam-first-release-status-03/result.json")
        if path.exists():
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            with os.fdopen(fd, "rb") as stream:
                meta = os.fstat(stream.fileno())
                assert stat.S_ISREG(meta.st_mode) and meta.st_uid == meta.st_gid == 0
                assert stat.S_IMODE(meta.st_mode) == 0o600 and meta.st_nlink == 1
                raw = stream.read(1025)
            assert len(raw) <= 1024
            if raw:
                result = json.loads(raw)
                assert set(result) == {"schema_version", "code", "phase"} and type(result["schema_version"]) is int and result["schema_version"] == 1
                assert result["code"] in SAFE_FAILURES | {"FIRST_RELEASE_REFUSED", "CUTOVER_VERIFIED"}
                assert result["phase"] in {p.value for p in Phase} | {"unavailable"}
        directory = Path("/var/lib/mrjam-cutover/first-deployment")
        try:
            phase = Checkpoint(directory).read().value
        except FileNotFoundError:
            phase = "absent"
        expected = {"schema_version": 1, "code": "CUTOVER_VERIFIED", "phase": Phase.OPEN.value}
        success = (value["ActiveState"] == "active" and value["SubState"] == "exited"
                   and value["ExecMainCode"] == 1 and value["ExecMainStatus"] == 0 and value["MainPID"] == 0
                   and result == expected and phase == Phase.OPEN.value)
        print(json.dumps({"schema_version": 1, "code": "FIRST_RELEASE_OBSERVED", "unit": value,
                          "result": result, "phase": phase, "deployment_verified": success}, sort_keys=True))
        return 0
    except BaseException:
        print('{"schema_version":1,"code":"FIRST_RELEASE_OBSERVATION_REFUSED"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
