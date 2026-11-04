"""Read only closed lifecycle metadata for the fixed resolver correction."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

CONTROLLER = "/nix/store/f0v9l1a6i7hj67y2mcwxa9h5i485gbnd-mrjam-resolver-update-001"
SYSTEMCTL = "/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl"
UNIT = "mrjam-resolver-update-20261103-01.service"


def main():
    try:
        assert len(sys.argv) == 1 and os.geteuid() == 0 and os.uname().nodename == "srv1982677"
        sys.path.insert(0, CONTROLLER + "/libexec")
        import resolver_update_adapter as adapter
        import configuration_update as controller
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
        path = Path("/run/mrjam-resolver-update-status-01/result.json")
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
                assert set(result) == {"schema_version", "code", "application_data_restored"} and type(result["schema_version"]) is int and result["schema_version"] == 1
                assert result["code"] in {"CONFIGURATION_VERIFIED", "CONFIGURATION_ALREADY_VERIFIED", "CONFIGURATION_RETURNED", "CONFIGURATION_ALREADY_RETURNED", "CONFIGURATION_UPDATE_REFUSED"}
                assert result["application_data_restored"] is False
        instance = adapter.Adapter()
        phase = instance.read_checkpoint() or "absent"
        pair = instance.observe()
        expected = {"schema_version": 1, "code": "CONFIGURATION_VERIFIED", "application_data_restored": False}
        success = (value["ActiveState"] == "active" and value["SubState"] == "exited"
                   and value["ExecMainCode"] == 1 and value["ExecMainStatus"] == 0 and value["MainPID"] == 0
                   and result == expected and phase == "complete" and pair == ("candidate", "candidate"))
        print(json.dumps({"schema_version": 1, "code": "CONFIGURATION_UPDATE_OBSERVED", "unit": value,
                          "result": result, "phase": phase, "configuration_verified": success}, sort_keys=True))
        return 0
    except BaseException:
        print('{"schema_version":1,"code":"CONFIGURATION_OBSERVATION_REFUSED"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
