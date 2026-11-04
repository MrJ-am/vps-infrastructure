"""Fixed post-release proposal entry. No caller-selected command or input path."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import lease

BINDING = "@BINDING@"
BINDING_SHA256 = "@BINDING_SHA256@"
BOOTSTRAP = "@BOOTSTRAP@/libexec/core.py"
GIT = "@GIT@/bin/git"
SELF = "@SELF@"
CURRENT = "/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git"
STATE = Path("/var/lib/mrjam-cutover/first-deployment")
SAFE_CODES = frozenset((
    "BINDING_HASH_REFUSED","BINDING_SHAPE_REFUSED","BINDING_REVISION_REFUSED","BINDING_DIGEST_REFUSED",
    "BINDING_SIZE_REFUSED","PROPOSAL_DIRECTORY_REFUSED","PROPOSAL_BUNDLE_REFUSED","PROPOSAL_BUNDLE_HEADER_REFUSED",
    "GIT_OPERATION_REFUSED","REFERENCE_SHAPE_REFUSED","MAIN_CHANGED","PROPOSAL_BRANCH_CONFLICT",
    "PROPOSAL_PARENT_REFUSED","PROPOSAL_TREE_REFUSED","PROPOSAL_DELTA_REFUSED","WORKFLOW_MODE_REFUSED",
    "WORKFLOW_BYTES_REFUSED","REFERENCE_OBSERVATION_CHANGED","REFERENCE_READBACK_REFUSED","FORGEJO_VERSION_REFUSED",
    "AUTHOR_IDENTITY_REFUSED","REPOSITORY_STATE_REFUSED","MAIN_PROTECTION_REFUSED","PULL_REQUEST_CONFLICT",
    "PULL_REQUEST_AUTHOR_REFUSED","PULL_REQUEST_TARGET_REFUSED","REPOSITORY_OBSERVATION_CHANGED","PULL_REQUEST_READBACK_REFUSED",
    "LEASE_LABEL_REFUSED","LEASE_OPERATION_REFUSED","LEASE_SQL_RESULT_REFUSED","LEASE_JOURNAL_WRITE_REFUSED",
    "LEASE_JOURNAL_REFUSED","LEASE_REVOCATION_REFUSED","TECHNICAL_ACCOUNT_REFUSED","LEASE_COLLISION",
    "LEASE_TOKEN_REFUSED","LEASE_STILL_AUTHENTICATES","PROPOSAL_INTERRUPTED","DEPLOYED_BASELINE_REFUSED","TRANSACTION_LOCK_REFUSED"))


def gate(bootstrap):
    core.require(all(os.path.realpath(path) == CURRENT for path in
        ("/run/current-system","/nix/var/nix/profiles/system")), "DEPLOYED_BASELINE_REFUSED")
    phase = bootstrap.parse(bootstrap.private_file(STATE/"phase.json",maximum=1024))
    core.require(type(phase) is dict and set(phase) == {"schema_version","phase","elapsed_seconds"}
        and type(phase["schema_version"]) is int and phase["schema_version"] == 1
        and phase["phase"] == "public-writes-open" and type(phase["elapsed_seconds"]) is int
        and phase["elapsed_seconds"] >= 0, "DEPLOYED_BASELINE_REFUSED")
    result = bootstrap.parse(bootstrap.private_file(Path("/run/mrjam-first-release-status-05/result.json"),maximum=1024))
    core.require(type(result) is dict and type(result.get("schema_version")) is int and result == {
        "schema_version":1,"code":"CUTOVER_VERIFIED","phase":"public-writes-open"}, "DEPLOYED_BASELINE_REFUSED")


def failure(error):
    return str(error) if isinstance(error,(core.Refused,lease.Refused)) and str(error) in SAFE_CODES else "RULES_PROPOSAL_REFUSED"


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0 or os.uname().nodename != "srv1982677":
        return 64
    resource.setrlimit(resource.RLIMIT_CORE,(0,0)); os.umask(0o077)
    def interrupted(*_):
        raise core.Refused("PROPOSAL_INTERRUPTED")
    saved = {number:signal.signal(number,interrupted) for number in (signal.SIGINT,signal.SIGTERM,signal.SIGALRM)}
    signal.alarm(420)
    fd = None
    try:
        spec = importlib.util.spec_from_file_location("qualified_bootstrap",BOOTSTRAP)
        bootstrap = importlib.util.module_from_spec(spec); spec.loader.exec_module(bootstrap)
        fd = os.open(STATE/"transaction.lock",os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK)
        info = os.fstat(fd)
        core.require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
            and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600,"TRANSACTION_LOCK_REFUSED")
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        gate(bootstrap)
        binding = core.Binding(Path(BINDING).read_bytes(),BINDING_SHA256)
        git = core.Git(GIT,SELF+"/bin/mrjam-rules-proposal-credential",SELF+"/hooks",binding)
        result = core.open_proposal(binding,git,bootstrap)
        gate(bootstrap)
        print(json.dumps(result,sort_keys=True,separators=(",",":")))
        return 0
    except Exception as error:
        print(json.dumps({"schema_version":1,"code":failure(error)},sort_keys=True,separators=(",",":")))
        return 1
    finally:
        if fd is not None: os.close(fd)
        signal.alarm(0)
        for number,handler in saved.items(): signal.signal(number,handler)


if __name__ == "__main__":
    raise SystemExit(main())
