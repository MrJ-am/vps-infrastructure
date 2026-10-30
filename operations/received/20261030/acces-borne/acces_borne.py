"""Création explicitement autorisée, puis usage d'une capacité SSH restreinte.

La clé privée neuve n'est jamais ouverte par ce programme : seuls ssh-keygen
et le client SSH l'utilisent. Aucun diagnostic distant n'est affiché/conservé.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shlex
import subprocess
import sys
import tempfile

BASE = Path(__file__).resolve().parent
PACKAGE = BASE.parent
SSH = "/run/current-system/sw/bin/ssh"
KEYGEN = "/run/current-system/sw/bin/ssh-keygen"
KEYDIR = BASE / ".identite-restreinte"
PRIVATE = KEYDIR / "id_ed25519"
CONFIG = BASE / "ssh-config"
OPERATION = "mrjam-inventory-v1"
ACCOUNT = "mrjam-inventory"
MAX_REPORT = 16384


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


remise = module("remise", PACKAGE / "remise_inventaire.py")
runner = module("runner", BASE / "runner.py")
installer = module("installer", BASE / "installer.py")


def fail(code):
    raise remise.ClosedFailure(code)


def quote_config(text):
    if any(c in text for c in "\n\r\0"):
        fail("LOCAL_CONFIG_REJECTED")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def prepare():
    if os.getuid() == 0 or os.geteuid() == 0:
        fail("LOCAL_NONPRIVILEGED_USER_REQUIRED")
    # Effective local reference only: ssh -G makes no production connection.
    config = subprocess.run([SSH, "-G", "vps"], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=10, check=False)
    if config.returncode:
        fail("LOCAL_CONFIG_UNAVAILABLE")
    fields = {}
    for line in config.stdout.decode().splitlines():
        key, _, value = line.partition(" ")
        if key in {"hostname", "port", "userknownhostsfile", "globalknownhostsfile", "checkhostip", "hostkeyalias"}:
            fields[key] = value
    if not all(k in fields for k in ("hostname", "port", "userknownhostsfile", "globalknownhostsfile")):
        fail("LOCAL_CONFIG_UNAVAILABLE")
    if not PRIVATE.exists():
        KEYDIR.mkdir(mode=0o700, exist_ok=False)
        result = subprocess.run([KEYGEN, "-q", "-t", "ed25519", "-N", "", "-C",
                                 "mrjam-inventory-borne-20261030", "-f", str(PRIVATE)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=15, check=False)
        if result.returncode:
            fail("KEY_CREATION_FAILED")
    # Read only the PUBLIC part of the new, dedicated credential.
    public = Path(str(PRIVATE) + ".pub").read_text()
    if not installer.public_key_allowed(public):
        fail("PUBLIC_KEY_REJECTED")
    lines = ["Host vps", "  User " + ACCOUNT,
             "  HostName " + quote_config(fields["hostname"]), "  Port " + fields["port"],
             "  IdentityFile " + quote_config(str(PRIVATE)),
             "  IdentitiesOnly yes", "  IdentityAgent none", "  BatchMode yes",
             "  StrictHostKeyChecking yes", "  UpdateHostKeys no", "  ConnectTimeout 15",
             "  ServerAliveInterval 10", "  ServerAliveCountMax 2", "  ForwardAgent no",
             "  ForwardX11 no", "  ClearAllForwardings yes", "  PermitLocalCommand no",
             "  ControlMaster no", "  ControlPath none", "  RequestTTY no"]
    for key in ("userknownhostsfile", "globalknownhostsfile"):
        paths = shlex.split(fields[key])
        if not paths or any(p in ("none", "/dev/null") for p in paths):
            fail("HOST_KEY_REFERENCE_REJECTED")
        lines.append("  " + key + " " + " ".join(quote_config(p) for p in paths))
    for key in ("checkhostip", "hostkeyalias"):
        if key in fields:
            lines.append("  " + key + " " + quote_config(fields[key]))
    CONFIG.write_text("\n".join(lines) + "\n")
    CONFIG.chmod(0o600)
    return public


def bootstrap_body(public):
    source = ("RUNNER_SOURCE = " + repr((BASE / "runner.py").read_text()) + "\n"
              + "PUBLIC_KEY = " + repr(public) + "\n" + (BASE / "installer.py").read_text())
    header = """set +x
exec >/dev/null 2>&1
set -u
[[ "$UID" -eq 0 && "$EUID" -eq 0 ]] || exit 40
mrjam_python_found=
for mrjam_python in /run/current-system/sw/bin/python3 /usr/bin/python3 /nix/store/*-python3-*/bin/python3; do
  [[ -x "$mrjam_python" ]] || continue
  if "$mrjam_python" -I -S -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
    mrjam_python_found=$mrjam_python
    break
  fi
done
[[ -n "$mrjam_python_found" ]] || exit 44
"$mrjam_python_found" -I -S - <<'MRJAM_INSTALLER'
"""
    return (header + source + "\nMRJAM_INSTALLER\n").encode()


def install_access(public):
    command = [SSH, *remise.options("root"), "-T", "vps",
               "env -u BASH_ENV -u ENV bash --noprofile --norc -s"]
    result = subprocess.run(command, input=bootstrap_body(public), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=60, check=False)
    codes = {40: "ROOT_ACCESS_UNAVAILABLE", 42: "ACCOUNT_OR_PATH_ALREADY_EXISTS",
             44: "REMOTE_PYTHON_311_REQUIRED", 45: "PUBLIC_KEY_REJECTED",
             46: "SSH_ACCOUNT_POLICY_UNSUITABLE", 47: "REMOTE_PYTHON_NOT_TRUSTED",
             48: "ACCOUNT_CREATION_FAILED", 49: "ACCOUNT_GROUPS_REJECTED",
             50: "ACCESS_FILE_OWNERSHIP_REJECTED", 51: "ACCESS_SETUP_FAILED"}
    if result.returncode:
        fail(codes.get(result.returncode, "SSH_SETUP_FAILED"))
    (BASE / "installation-reussie").write_text("ACCOUNT_CREATED_WITH_RESTRICTED_KEY\n")


def output_limit():
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_REPORT + 1, MAX_REPORT + 1))


def bounded_call(operation, data):
    # A separate config offers ONLY the new key, never the root identity.
    command = [SSH, "-F", str(CONFIG), "-T", "vps"]
    if operation is not None:
        command.append(operation)
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(command, input=data, stdout=output, stderr=subprocess.DEVNULL,
                                timeout=90, check=False, preexec_fn=output_limit)
        length = os.fstat(output.fileno()).st_size
        if result.returncode != 0:
            return result.returncode, length, b""
        output.seek(0)
        return result.returncode, length, output.read(MAX_REPORT + 1)


def check_boundary():
    for operation, data, expected in (("mrjam-invalid-operation", b"", 64),
                                      (None, b"", 64), (OPERATION, b"INVALID", 65)):
        status, size, _ = bounded_call(operation, data)
        if status != expected or size != 0:
            fail("BOUNDARY_VERIFICATION_FAILED")
    (BASE / "frontiere-verifiee").write_text("INVALID_COMMAND_SHELL_AND_PAYLOAD_REJECTED\n")


def collect(files):
    if not (BASE / "frontiere-verifiee").is_file():
        fail("BOUNDARY_VERIFICATION_REQUIRED")
    target = PACKAGE / remise.OUTPUT
    if target.exists() or target.is_symlink():
        fail("RESULT_ALREADY_EXISTS")
    payload = runner.MAGIC + b"".join(files[name] for name, _, _ in runner.RUNTIME)
    runner.unpack(payload)
    status, size, data = bounded_call(OPERATION, payload)
    if status:
        codes = {64: "ACCESS_DENIED", 65: "PACKAGE_REJECTED_REMOTELY", 66: "REMOTE_INTEGRITY_FAILED",
                 67: "REMOTE_PIPELINE_FAILED", 68: "REMOTE_REPORT_REJECTED", 69: "REMOTE_TIMEOUT",
                 70: "REMOTE_ORDINARY_OPERATION_FAILED"}
        fail(codes.get(status, "SSH_INVENTORY_FAILED"))
    if not 0 < size <= MAX_REPORT:
        fail("LOCAL_REPORT_REJECTED")
    with tempfile.TemporaryDirectory(prefix=".retour-borne-", dir=PACKAGE) as temp:
        stage = Path(temp)
        for name in ("validate_report.py", "inventory.schema.json"):
            (stage / name).write_bytes(files[name])
        result = subprocess.run([sys.executable, "-I", "-S", str(stage / "validate_report.py")],
                                input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=10, check=False)
        if result.returncode or not 0 < len(result.stdout) <= MAX_REPORT:
            fail("LOCAL_REPORT_REJECTED")
        validated = stage / remise.OUTPUT
        validated.write_bytes(result.stdout)
        os.link(validated, target)


def main():
    os.umask(0o077)
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ("--prepare", "--install", "--check-boundary", "--run"):
            fail("UNSUPPORTED_ARGUMENTS")
        files = remise.verify_package(PACKAGE)
        if sys.argv[1] in ("--prepare", "--install"):
            public = prepare()
            if sys.argv[1] == "--install":
                install_access(public)
                code = "RESTRICTED_ACCOUNT_CREATED"
            else:
                code = "ACCESS_PREPARED_LOCALLY"
        elif sys.argv[1] == "--check-boundary":
            check_boundary()
            code = "BOUNDARY_VERIFIED"
        else:
            collect(files)
            code = "REPORT_VALIDATED"
        print(json.dumps({"status": "ok", "code": code}, separators=(",", ":")))
        return 0
    except remise.ClosedFailure as error:
        print(json.dumps({"status": "failed", "code": error.code}, separators=(",", ":")))
        return 1
    except BaseException:
        print('{"status":"failed","code":"LOCAL_ACCESS_OPERATION_FAILED"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
