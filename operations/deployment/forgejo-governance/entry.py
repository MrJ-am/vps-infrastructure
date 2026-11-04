"""Generated entry: fixed binding, tools, operation and root-only invocation."""
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core

BINDING = "@BINDING@"
BINDING_SHA256 = "@BINDING_SHA256@"
OPERATION = "@OPERATION@"
GIT = "@GIT@/bin/git"
CREDENTIAL_HELPER = "@SELF@/bin/mrjam-forgejo-git-credential"
BOOTSTRAP = "@BOOTSTRAP@/libexec/core.py"


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0 or os.uname().nodename != "srv1982677":
        return 64
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    def interrupted(*_):
        raise core.Refused("GOVERNANCE_INTERRUPTED")
    for number in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
        signal.signal(number, interrupted)
    signal.alarm(1800 if OPERATION == "adopt" else 240)
    try:
        binding = core.Binding(Path(BINDING).read_bytes(), BINDING_SHA256)
        inputs = core.verify_source_inputs(binding)
        if OPERATION == "probe":
            result = inputs
        else:
            core.require(OPERATION == "adopt", "GENERATED_OPERATION_REFUSED")
            spec = importlib.util.spec_from_file_location("technical_bootstrap", BOOTSTRAP)
            bootstrap = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bootstrap)
            phase = bootstrap.parse(bootstrap.private_file(Path("/var/lib/mrjam-cutover/first-deployment/phase.json"), maximum=1024))
            core.require(type(phase) is dict and set(phase) == {"schema_version", "phase", "elapsed_seconds"}
                         and type(phase["schema_version"]) is int and phase["schema_version"] == 1
                         and phase["phase"] == "state-adopted" and type(phase["elapsed_seconds"]) is int
                         and phase["elapsed_seconds"] >= 0, "ADOPTED_CHECKPOINT_REQUIRED")
            result = core.adopt(binding, core.Git(GIT, CREDENTIAL_HELPER), bootstrap)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, (core.Refused, core.reconcile.Refused)) else "GOVERNANCE_OPERATION_REFUSED"
        if not re.fullmatch(r"[A-Z_]{1,80}", code):
            code = "GOVERNANCE_OPERATION_REFUSED"
        print(json.dumps({"schema_version":1,"code":code},sort_keys=True,separators=(",", ":")))
        return 1
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
