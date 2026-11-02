"""Independent actual Nix import and inactive unit delivery in an invented VM."""
import base64
import fcntl
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import traceback

ROOT = Path("/etc/delivery-fixture")
WORK = Path("/var/lib/synthetic-provision-delivery")
UNIT = Path("/run/systemd/system/mrjam-kanidm-worker-provision.service")
MARKER = Path("/run/synthetic-provision-started")


def require(value, code):
    if not value:
        raise RuntimeError(code)


def command(arguments, checked=True):
    result = subprocess.run(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=30, check=False)
    if checked:
        require(result.returncode == 0, "FIXTURE_COMMAND_FAILED")
    return result


def require_inactive():
    result = command(["systemctl", "show", "mrjam-kanidm-worker-provision.service",
                      "--property=LoadState,ActiveState,MainPID"])
    fields = dict(line.split("=",1) for line in result.stdout.decode().splitlines())
    require(fields == {"LoadState":"loaded","ActiveState":"inactive","MainPID":"0"}, "IMPLICIT_UNIT_ACTIVATION")
    require(not MARKER.exists(), "INERT_UNIT_WAS_EXECUTED")


def qualify():
    require(os.geteuid() == 0 and ROOT.joinpath("synthetic-only").read_text() == "INVENTED_INERT_DELIVERY_VM_ONLY\n",
            "SYNTHETIC_VM_ONLY")
    spec = importlib.util.spec_from_file_location("sealed_receiver_under_test", ROOT/"receiver.py")
    receiver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(receiver)
    require(receiver.RELEASE is None, "UNSEALED_SOURCE_REQUIRED")
    # The only environmental substitutions: this VM's real generation and its
    # invented private delivery directory. No command/import/unit helper mocked.
    receiver.PREVIOUS = os.path.realpath("/run/current-system")
    receiver.DIRECTORY = WORK
    encoded = json.loads(ROOT.joinpath("bundle.json").read_bytes())
    release = json.loads(base64.b64decode(encoded["manifest_base64"],validate=True))
    archive = gzip.decompress(base64.b64decode(encoded["export_gzip_base64"],validate=True))
    require(hashlib.sha256(archive).hexdigest() == release["export_sha256"] and len(archive) == release["export_bytes"],
            "INVENTED_BUNDLE_INTEGRITY")
    require(len(release["store_paths"]) == 2 and len(archive) < 65536, "INVENTED_BUNDLE_SCOPE")
    require(not UNIT.exists() and not UNIT.is_symlink(), "UNIT_PREEXISTED")
    for path in release["store_paths"]:
        require(not Path(path).exists(), "INVENTED_STORE_ROOT_PREINSTALLED")
        status=command(["nix-store","--check-validity",path],checked=False)
        require(status.returncode != 0, "INVENTED_STORE_ROOT_ALREADY_REGISTERED")
    checks = ["two-invented-roots-absent-from-private-vm-store"]

    for payload in (archive[:-1], archive+b"EXTRA", b"x"+archive[1:]):
        try:
            receiver.deliver(release,io.BytesIO(payload))
        except receiver.Refused:
            pass
        else:
            raise RuntimeError("UNVERIFIED_EXPORT_ACCEPTED")
        require(not UNIT.exists() and not UNIT.is_symlink(), "CORRUPTION_INSTALLED_UNIT")
        require(not WORK.joinpath("export.nar").exists(), "CORRUPTION_PUBLISHED_EXPORT")
        require(all(not Path(path).exists() for path in release["store_paths"]), "CORRUPTION_REACHED_NIX_IMPORT")
    checks.append("truncation-extra-bytes-corruption-refused-before-real-import")

    expected={"schema_version":1,"code":"HUMAN_LOGIN_TOOL_INSTALLED","application_activation":False,"credential_creation":False}
    require(receiver.deliver(release,io.BytesIO(archive)) == expected, "DELIVERY_RESULT")
    require(os.readlink(UNIT) == release["unit_store"]+"/"+receiver.UNIT, "INSTALLED_UNIT_TARGET")
    for path in release["store_paths"]:
        require(Path(path).exists(), "ROOT_NOT_IMPORTED")
        command(["nix-store","--verify-path",path])
    require(hashlib.sha256(UNIT.read_bytes()).hexdigest() == release["unit_sha256"], "UNIT_BYTES_CHANGED")
    require_inactive()
    checks.append("real-nix-import-verify-path-and-manager-reload-with-inactive-unit")

    unit_inode=UNIT.lstat().st_ino
    require(receiver.deliver(release,io.BytesIO(archive)) == expected, "REPEAT_RESULT")
    require(UNIT.lstat().st_ino == unit_inode, "REPEAT_REPLACED_UNIT_LINK")
    require_inactive()
    checks.append("identical-repeated-import-preserves-unit-and-no-activation")

    # A distinct open-file description holds a real flock, as a concurrent
    # receiver would. The tested function must refuse before reading any byte.
    class UnreadableInput:
        def read(self,_):
            raise AssertionError("CONCURRENT_INPUT_WAS_READ")
    descriptor=os.open(WORK,os.O_RDONLY|os.O_DIRECTORY)
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            receiver.deliver(release,UnreadableInput())
        except BlockingIOError:
            pass
        else:
            raise RuntimeError("CONCURRENT_DELIVERY_ACCEPTED")
    finally:
        os.close(descriptor)
    require_inactive()
    checks.append("real-directory-flock-refuses-concurrent-stream-before-read")

    target=os.readlink(UNIT)
    UNIT.unlink()
    foreign=b"[Unit]\nDescription=INVENTED_FOREIGN_UNIT_KEEP\n"
    UNIT.write_bytes(foreign)
    try:
        receiver.deliver(release,io.BytesIO(archive))
    except OSError:
        pass
    else:
        raise RuntimeError("FOREIGN_REGULAR_UNIT_REPLACED")
    require(UNIT.read_bytes() == foreign and not UNIT.is_symlink(), "FOREIGN_UNIT_NOT_PRESERVED")
    UNIT.unlink()
    UNIT.symlink_to("/INVENTED_FOREIGN_TARGET")
    try:
        receiver.deliver(release,io.BytesIO(archive))
    except receiver.Refused:
        pass
    else:
        raise RuntimeError("FOREIGN_LINK_REPLACED")
    require(os.readlink(UNIT) == "/INVENTED_FOREIGN_TARGET", "FOREIGN_LINK_NOT_PRESERVED")
    UNIT.unlink()
    UNIT.symlink_to(target)
    command(["systemctl","daemon-reload"])
    require_inactive()
    checks.append("foreign-regular-unit-and-link-never-replaced")
    return {"passed":True,"checks":checks,"source_functions_unmodified":True,
            "real_store_import":True,"unit_started":False,"credentials_created":False,
            "synthetic_package":release["package"],"synthetic_unit":release["unit_store"]}


if __name__ == "__main__":
    try:
        result=qualify()
    except Exception as error:
        locations=[{"file":Path(frame.filename).name,"line":frame.lineno,"function":frame.name}
                   for frame in traceback.extract_tb(error.__traceback__)]
        print(json.dumps({"passed":False,"code":str(error) if isinstance(error,RuntimeError) else type(error).__name__,
                          "synthetic_failure_locations":locations}))
        raise SystemExit(1)
    print(json.dumps(result,sort_keys=True))
