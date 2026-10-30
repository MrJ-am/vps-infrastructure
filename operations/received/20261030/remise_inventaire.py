"""Remise manuelle depuis Spectre. Ce programme ne constitue pas une ACL.

Aucun appel distant n'est autorisé à l'agent avec le canal SSH général actuel.
Usage humain : remise-inventaire.sh NOM_D_UN_COMPTE_EXISTANT_NON_PRIVILEGIE
Sans compte, avec root ou avec --verify-only : aucune connexion.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import resource
import stat
import subprocess
import sys
import tarfile
import tempfile
import uuid


ARCHIVE = "mrjam-inventaire-borne-20261030.tar.gz"
ARCHIVE_SHA256 = "47c0c620a241cb37dd44601f21322badcb18aed0d4e0161a3e891ef795514b9e"
RUNTIME = ("inventory.py", "validate_report.py", "inventory.schema.json")
CONTENTS = frozenset((*RUNTIME, "AGENTS.md", "inventaire-borne.org", "remise.json",
                      "qualification.json", "test_inventory.py", "test_validate_report.py",
                      "SHA256SUMS"))
OUTPUT = "inventaire-borne-filtre.json"
SSH = "/run/current-system/sw/bin/ssh"
SCP = "/run/current-system/sw/bin/scp"
SSH_ALIAS = "vps"
MAX_REPORT = 16_384


class ClosedFailure(Exception):
    def __init__(self, code: str):
        self.code = code


def regular_bytes(path: Path, limit: int) -> bytes:
    # Do not follow a replaced file or read beyond the declared size bound.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError()
        data = handle.read(limit + 1)
        if len(data) > limit:
            raise ValueError()
        return data


def verify_package(base: Path) -> dict[str, bytes]:
    """Recheck the original archive, all manifest rows, and extracted bytes."""
    try:
        archive = regular_bytes(base / ARCHIVE, 1_000_000)
        if hashlib.sha256(archive).hexdigest() != ARCHIVE_SHA256:
            raise ValueError()
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
            members = bundle.getmembers()
            if len(members) != len(CONTENTS) or {m.name for m in members} != CONTENTS:
                raise ValueError()
            if any(not m.isfile() or not 0 <= m.size <= 1_000_000 for m in members):
                raise ValueError()
            files = {m.name: bundle.extractfile(m).read() for m in members}
        package = base / "paquet-verifie"
        if package.is_symlink() or not package.is_dir():
            raise ValueError()
        for name, data in files.items():
            if regular_bytes(package / name, 1_000_000) != data:
                raise ValueError()
        seen = set()
        for row in files["SHA256SUMS"].decode("ascii").splitlines():
            match = re.fullmatch(r"([a-f0-9]{64})  ([A-Za-z0-9_.-]+)", row)
            if not match:
                raise ValueError()
            digest, name = match.groups()
            if name not in CONTENTS - {"SHA256SUMS"} or name in seen:
                raise ValueError()
            if hashlib.sha256(files[name]).hexdigest() != digest:
                raise ValueError()
            seen.add(name)
        if seen != CONTENTS - {"SHA256SUMS"}:
            raise ValueError()
        return files
    except FileNotFoundError:
        raise ClosedFailure("PACKAGE_UNAVAILABLE") from None
    except Exception:
        raise ClosedFailure("PACKAGE_INTEGRITY_FAILED") from None


def options(account: str) -> list[str]:
    # Reuse the existing alias and identity references. Never read a private key.
    # The explicit user overrides the alias's current User root for SSH and SCP.
    return [
        "-o", f"User={account}",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "UpdateHostKeys=no",
        "-o", "ConnectTimeout=15",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=2",
        "-o", "ForwardAgent=no",
        "-o", "ForwardX11=no",
        "-o", "ClearAllForwardings=yes",
        "-o", "PermitLocalCommand=no",
        "-o", "RemoteCommand=none",
        "-o", "ControlMaster=no",
        "-o", "ControlPath=none",
    ]


def file_limit() -> None:
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_REPORT, MAX_REPORT))


def quiet_run(argv: list[str], *, body: bytes | None = None,
              limit_file: bool = False) -> int:
    """Never capture/return SSH, SCP or system diagnostic text."""
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "timeout": 90, "check": False, "close_fds": True}
    if body is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = body
    if limit_file:
        kwargs["preexec_fn"] = file_limit
    try:
        return subprocess.run(argv, **kwargs).returncode
    except subprocess.TimeoutExpired:
        raise ClosedFailure("TRANSPORT_TIMEOUT") from None
    except OSError:
        raise ClosedFailure("TRANSPORT_UNAVAILABLE") from None


REMOTE_PREFLIGHT = """set +x
exec >/dev/null 2>&1
set -u
set -o pipefail
umask 077
[[ "$UID" -ne 0 && "$EUID" -ne 0 ]] || exit 41
command -v python3 >/dev/null 2>&1 || exit 42
python3 -I -S -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || exit 42
"""


def remote_prepare(directory: str) -> bytes:
    # Directory is generated internally, never accepted from a caller/remote.
    assert re.fullmatch(r"\.mrjam-inventaire-[a-f0-9]{32}", directory)
    return (REMOTE_PREFLIGHT + f"mkdir -- '{directory}' || exit 43\n").encode()


def remote_inventory(directory: str, files: dict[str, bytes]) -> bytes:
    assert re.fullmatch(r"\.mrjam-inventaire-[a-f0-9]{32}", directory)
    expected = {name: hashlib.sha256(files[name]).hexdigest() for name in RUNTIME}
    # Only fixed file names/digests enter the generated Python verification.
    # No SHA256SUMS file or additional script is transferred to the VPS.
    verify = f"""cd -- '{directory}' || exit 43
python3 -I -S - <<'MRJAM_VERIFY' || exit 44
import hashlib, os, stat, sys
expected = {expected!r}
try:
    for name, digest in expected.items():
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError()
            if info.st_size > 65536 or hashlib.sha256(handle.read(65537)).hexdigest() != digest:
                raise ValueError()
except Exception:
    sys.exit(1)
MRJAM_VERIFY
set -o noclobber
set -o pipefail
python3 -I -S ./inventory.py 2>/dev/null |
  python3 -I -S ./validate_report.py 2>/dev/null \\
    > inventaire-borne-filtre.json
mrjam_pipeline_status=$?
[[ "$mrjam_pipeline_status" -eq 0 ]] || exit 45
exit 0
"""
    return (REMOTE_PREFLIGHT + verify).encode()


def require_remote_success(code: int, fallback: str) -> None:
    if code:
        known = {
            41: "EXISTING_NONPRIVILEGED_ACCOUNT_REQUIRED",
            42: "REMOTE_PYTHON_311_REQUIRED",
            43: "REMOTE_WORK_DIRECTORY_UNAVAILABLE",
            44: "REMOTE_INTEGRITY_FAILED",
            45: "REMOTE_PIPELINE_FAILED",
        }
        raise ClosedFailure(known.get(code, fallback))


def execute(base: Path, account: str, files: dict[str, bytes]) -> None:
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", account) or account == "root":
        raise ClosedFailure("EXISTING_NONPRIVILEGED_ACCOUNT_REQUIRED")
    if os.getuid() == 0 or os.geteuid() == 0:
        raise ClosedFailure("LOCAL_NONPRIVILEGED_USER_REQUIRED")
    if not all(os.access(tool, os.X_OK) for tool in (SSH, SCP)):
        raise ClosedFailure("LOCAL_TRANSPORT_UNAVAILABLE")
    if (base / OUTPUT).exists() or (base / OUTPUT).is_symlink():
        raise ClosedFailure("RESULT_ALREADY_EXISTS")
    common = options(account)
    ssh = [SSH, *common, "-T", SSH_ALIAS,
           "env -u BASH_ENV -u ENV bash --noprofile --norc -s"]
    directory = ".mrjam-inventaire-" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix=".remise-locale-", dir=base) as temp:
        stage = Path(temp)
        # Snapshot the bytes already verified against the pinned archive.
        for name in RUNTIME:
            (stage / name).write_bytes(files[name])
        require_remote_success(quiet_run(ssh, body=remote_prepare(directory)),
                               "SSH_PREPARATION_FAILED")
        if quiet_run([SCP, *common, "-q", *(str(stage / n) for n in RUNTIME),
                      f"{SSH_ALIAS}:./{directory}/"]):
            raise ClosedFailure("UPLOAD_FAILED")
        require_remote_success(quiet_run(ssh, body=remote_inventory(directory, files)),
                               "SSH_INVENTORY_FAILED")
        candidate = stage / "retour-en-attente.json"
        # This transfer is reachable ONLY after successful remote pipefail.
        if quiet_run([SCP, *common, "-q", f"{SSH_ALIAS}:./{directory}/{OUTPUT}",
                      str(candidate)], limit_file=True):
            raise ClosedFailure("DOWNLOAD_FAILED")
        try:
            received = regular_bytes(candidate, MAX_REPORT)
            result = subprocess.run(
                [sys.executable, "-I", "-S", str(stage / "validate_report.py")],
                input=received, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                check=False, timeout=10, close_fds=True,
            )
        except Exception:
            raise ClosedFailure("LOCAL_REPORT_REJECTED") from None
        if result.returncode != 0 or not 0 < len(result.stdout) <= MAX_REPORT:
            raise ClosedFailure("LOCAL_REPORT_REJECTED")
        validated = stage / OUTPUT
        validated.write_bytes(result.stdout)
        # Atomic publication, no overwrite: a failed run cannot publish a report.
        os.link(validated, base / OUTPUT)


def main(args: list[str], base: Path) -> int:
    os.umask(0o077)
    try:
        if len(args) > 1 or (args and args[0].startswith("-") and args != ["--verify-only"]):
            raise ClosedFailure("UNSUPPORTED_ARGUMENTS")
        files = verify_package(base)
        if args == ["--verify-only"]:
            code = "PACKAGE_VERIFIED"
        elif not args:
            raise ClosedFailure("EXISTING_NONPRIVILEGED_ACCOUNT_REQUIRED")
        else:
            execute(base, args[0], files)
            code = "REPORT_VALIDATED"
        print(json.dumps({"status": "ok", "code": code}, separators=(",", ":")))
        return 0
    except ClosedFailure as failure:
        print(json.dumps({"status": "failed", "code": failure.code}, separators=(",", ":")))
        return 1
    except BaseException:
        print('{"status":"failed","code":"LOCAL_EXECUTION_FAILED"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], Path(__file__).resolve().parent))
