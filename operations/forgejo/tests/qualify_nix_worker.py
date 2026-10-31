#!/usr/bin/env python3
"""Run the exact Nix verifier closure using the qualified host bwrap launcher.

This is a Cloud-only fixture adapter, not a production entrypoint. Store paths
are exported from the local synthetic Nix volume and verified there before
use. Only mount origins change; targets, flags, seccomp and artifact collection
are the worker implementation. NixOS/socket/cgroup behavior is tested in the
separate systemd VM, not inferred from this host test.
"""
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

spec = importlib.util.spec_from_file_location("worker", Path(__file__).parents[1] / "worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
BWRAP = Path("/usr/bin/bwrap")
BWRAP_SHA256 = "573236e5328ac2ebb08f59ae3a9805b4f8d12bdef14be8af4450d5463294985f"


def require(value, code):
    if not value:
        raise RuntimeError(code)


def main(*, diagnostic=False, candidate_diagnostics=False, http_diagnostic=False, output_directory=None):
    require(not candidate_diagnostics or diagnostic, "DIAGNOSTIC_MODE_REQUIRED")
    require(not http_diagnostic or candidate_diagnostics, "DIAGNOSTIC_MODE_REQUIRED")
    require(len(sys.argv) == 2 and os.getuid() != 0, "CLOUD_FIXTURE_REQUIRED")
    exported = Path(sys.argv[1]).absolute()
    require(re.fullmatch(r"/workspace/shared/mrjam-declarative-nix/worker-[A-Za-z0-9_-]+", str(exported)), "INVALID_FIXTURE_ROOT")
    require(exported.is_dir() and not exported.is_symlink(), "INVALID_FIXTURE_ROOT")
    require(hashlib.sha256(BWRAP.read_bytes()).hexdigest() == BWRAP_SHA256, "HOST_LAUNCHER_CHANGED")
    raw = worker.checked_bytes(exported / "export.json", 1048576)
    record = worker.parse(raw)
    worker.exact(record, ("schema_version", "scope", "configuration", "proposal_sha256", "paths"))
    require(record["schema_version"] == 1 and record["scope"] == "local-public-code-fixture", "INVALID_EXPORT")
    configuration = worker.policy(record["configuration"])
    require(type(record["paths"]) is list and 0 < len(record["paths"]) <= 1024, "INVALID_EXPORT")
    paths = []
    for entry in record["paths"]:
        worker.exact(entry, ("path", "nar_hash", "verified_after_copy"))
        require(worker.STORE.fullmatch(entry["path"]) and re.fullmatch(r"sha256-[A-Za-z0-9+/]{43}=", entry["nar_hash"])
                and entry["verified_after_copy"] is True, "INVALID_EXPORT")
        target = exported / entry["path"].removeprefix("/")
        metadata = os.lstat(target)
        require(metadata.st_uid == 0 and not metadata.st_mode & 0o222, "UNTRUSTED_STORE_EXPORT")
        paths.append(entry["path"])
    require(len(paths) == len(set(paths)) and configuration["validator_store"] in paths, "INVALID_EXPORT")
    source = worker.verify_input(exported / "input", record["proposal_sha256"], configuration["rules_revision"])
    destination = exported.parent if output_directory is None else Path(output_directory)
    if output_directory is not None:
        require(destination == exported.parent / "qualifier-uid-59990" and os.getuid() == 59990,
                "ISOLATED_UID_FIXTURE_REQUIRED")
        metadata = os.lstat(destination)
        require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == 59990 and metadata.st_mode & 0o777 == 0o700,
                "ISOLATED_UID_OUTPUT_REFUSED")
    if diagnostic:
        output_root = Path(tempfile.mkdtemp(prefix=exported.name + "-diagnostic-", dir=destination))
    else:
        output_root = destination / (exported.name + "-outputs")
        output_root.mkdir(mode=0o700) # Never replace an earlier receipt or artifact.
    if diagnostic:
        # Same explicit synthetic-only technique as the VM diagnostic variant.
        # Expose only the pinned supervisor's stderr; candidate commands still
        # discard stdout/stderr. Never turn this run into qualification evidence.
        diagnostic_source = inspect.getsource(worker.execute)
        require(diagnostic_source.count("stderr=subprocess.DEVNULL") == 1, "DIAGNOSTIC_SOURCE_CHANGED")
        namespace = dict(vars(worker))
        exec(compile(diagnostic_source.replace("stderr=subprocess.DEVNULL", "stderr=None"), "<synthetic-worker-diagnostic>", "exec"), namespace)
        worker.execute = namespace["execute"]
    overlays = []
    if candidate_diagnostics:
        # Public source and invented test data only. Keep the original closure
        # immutable and make the deviation explicit; this path always returns 2.
        library = configuration["validator_store"] + "/lib"
        runner = (exported / library.removeprefix("/") / "runner.py").read_text()
        match = re.search(r'^RUNTIME = Path\("(/nix/store/[a-z0-9]{32}-mrjam-verifier-runtime.json)"\)$', runner, re.M)
        require(match is not None, "DIAGNOSTIC_RUNTIME_CHANGED")
        runtime = worker.parse((exported / match[1].removeprefix("/")).read_bytes())
        require(worker.STORE.fullmatch(runtime["support"]), "DIAGNOSTIC_SUPPORT_CHANGED")
        for index, target in enumerate((library + "/sandbox.py", runtime["support"] + "/sandbox.py", runtime["support"] + "/pg_stage.py")):
            original = (exported / target.removeprefix("/")).read_text()
            require("stderr=subprocess.DEVNULL" in original, "DIAGNOSTIC_SOURCE_CHANGED")
            changed = original.replace("stdout=subprocess.DEVNULL", "stdout=None").replace("stderr=subprocess.DEVNULL", "stderr=None")
            overlay = output_root / ("diagnostic-" + str(index) + ".py")
            overlay.write_text(changed)
            overlay.chmod(0o400)
            overlays.extend(("--ro-bind", str(overlay), target))
        if http_diagnostic:
            binary = Path("/workspace/shared/mrjam-declarative-nix/runtime-export-20261031-02/mrjam-server")
            require(hashlib.sha256(binary.read_bytes()).hexdigest() == "7d91514354a124ea2e1e72b3841d6d9870dd7e8db6e700f07a3e59612a20b30c", "DIAGNOSTIC_BINARY_CHANGED")
            start, end = runner.index("    def rust(self):"), runner.index("    def http(self):")
            replacement = '''    def rust(self):
        self.server_source = self.source("platform")
        self.server_job = self.job("rust")
        self.server = self.private / "server"
        shutil.copyfile("/work/diagnostic-server", self.server)
        self.server.chmod(0o500)

'''
            runner = runner[:start] + replacement + runner[end:]
            runner = runner.replace("stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL", "stdout=None, stderr=None")
            runner = runner.replace("stdout=subprocess.DEVNULL,\n                                 stderr=subprocess.DEVNULL", "stdout=None,\n                                 stderr=None")
            require(runner.count("    verifier.elm()") == 1, "DIAGNOSTIC_MAIN_CHANGED")
            runner = runner.replace("    verifier.elm()", '    raise Refused("DIAGNOSTIC_HTTP_FINISHED_NO_QUALIFICATION")')
            overlays.extend(("--ro-bind", str(binary), "/work/diagnostic-server"))
        marker = '        require(code == 0, "CHECK_FAILED_" + name.upper().replace("-", "_"))'
        require(runner.count(marker) == 1, "DIAGNOSTIC_CHECK_CHANGED")
        measurement = ('        space = os.statvfs(WORK)\n'
                       '        print(json.dumps({"diagnostic_storage": {"step": name, "returncode": code, '
                       '"capacity_bytes": space.f_blocks * space.f_frsize, '
                       '"available_bytes": space.f_bavail * space.f_frsize}}), file=sys.stderr)\n')
        overlay = output_root / "diagnostic-runner.py"
        overlay.write_text(runner.replace(marker, measurement + marker))
        overlay.chmod(0o400)
        overlays.extend(("--ro-bind", str(overlay), library + "/runner.py"))
    outputs = {name: os.memfd_create("mrjam-qualified-" + name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING) for name, _ in worker.ARTIFACTS}
    started = time.monotonic()
    try:
        def command(channel, seccomp_fd):
            arguments = worker.command(configuration, paths, worker.INPUT_ROOT / record["proposal_sha256"], channel=channel, seccomp=seccomp_fd)
            arguments[0] = str(BWRAP)
            for index, argument in enumerate(arguments[:-1]):
                if argument == "--ro-bind":
                    origin = arguments[index + 1]
                    if origin in paths:
                        arguments[index + 1] = str(exported / origin.removeprefix("/"))
                    elif origin == str(worker.INPUT_ROOT / record["proposal_sha256"]):
                        arguments[index + 1] = str(source)
                    else:
                        raise RuntimeError("UNEXPECTED_MOUNT")
            if overlays:
                position = arguments.index(configuration["validator_store"] + "/bin/mrjam-validate")
                arguments[position:position] = overlays
            return arguments
        passed = worker.run_with_artifacts(command, outputs)
        if diagnostic:
            print(json.dumps({"decision": "diagnostic-only", "supervisor_returned_success": passed,
                              "qualification_passed": False, "production_access": False,
                              "http_only_reused_binary": http_diagnostic}))
            return 2
        require(passed, "NIX_VALIDATOR_REFUSED")
        artifacts = worker.seal_artifacts(outputs)
        for entry in artifacts:
            fd = outputs[entry["name"]]
            target = os.open(output_root / entry["name"], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
            try:
                while block := os.read(fd, 65536):
                    require(os.write(target, block) == len(block), "ARTIFACT_STORAGE_FAILED")
                os.fsync(target)
            finally:
                os.close(target)
        receipt = {"decision": "passed", "scope": "local synthetic Nix verifier and worker namespace protocol",
                   "proposal_sha256": record["proposal_sha256"], "rules_revision": configuration["rules_revision"],
                   "validator_store": configuration["validator_store"], "export_sha256": hashlib.sha256(raw).hexdigest(),
                   "worker_sha256": hashlib.sha256((Path(__file__).parents[1] / "worker.py").read_bytes()).hexdigest(),
                   "host_bwrap_sha256": BWRAP_SHA256, "artifacts": artifacts, "duration_seconds": round(time.monotonic() - started, 3),
                   "fixture_uid": os.getuid(), "isolated_uid_fixture": output_directory is not None,
                   "limitations": [("Pinned Nix bwrap runs under a dedicated local container UID; only exported mount origins change" if output_directory is not None else "Host bwrap 0.12.0 substitutes only the launcher and exported mount origins"), "No NixOS socket, cgroup or production authority is inferred", "Source and closure fixtures remain root-owned read-only for the entire run"]}
        with (output_root / "qualification.json").open("x") as stream:
            json.dump(receipt, stream, sort_keys=True)
            stream.write("\n")
        print(json.dumps(receipt, sort_keys=True))
        return 0
    finally:
        for fd in outputs.values():
            os.close(fd)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        code = str(error) if type(error) in (RuntimeError, worker.Refused) and re.fullmatch(r"[A-Z_]+", str(error)) else "QUALIFICATION_FAILED"
        print(json.dumps({"decision": "failed", "code": code}))
        raise SystemExit(1)
