#!/usr/bin/env python3
"""Real rootless Linux namespace checks; entirely invented host canaries.

Host Bubblewrap 0.12.0 is pinned by content hash here. The NixOS service and
Nix-store validator package are distinct tests: this script qualifies namespace
semantics, not VPS resources or the complete production execution chain.
"""
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("worker", ROOT / "worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
BWRAP = Path("/usr/bin/bwrap")
BWRAP_SHA256 = "573236e5328ac2ebb08f59ae3a9805b4f8d12bdef14be8af4450d5463294985f"


def require(value, code):
    if not value:
        raise RuntimeError(code)


def main():
    require(os.getuid() != 0, "UNPRIVILEGED_HOST_REQUIRED")
    require(hashlib.sha256(BWRAP.read_bytes()).hexdigest() == BWRAP_SHA256, "HOST_BUBBLEWRAP_CHANGED")
    require(subprocess.check_output([str(BWRAP), "--version"]).strip() == b"bubblewrap 0.12.0", "VERSION_CHANGED")
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(36, 1, 0, 0, 0) == 0, "SUBREAPER_REQUIRED")
    source_parent = Path(tempfile.mkdtemp(prefix="mrjam-worker-namespace-"))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(0.1)
    port = listener.getsockname()[1]
    checks = {}
    try:
        source = source_parent / "input"
        source.mkdir()
        canary = source_parent / "private-canary"
        canary.write_text("INVENTED_HOST_ONLY")
        (source / "readonly").write_text("synthetic code input")
        host_net = os.stat("/proc/self/ns/net").st_ino
        host_pid = os.stat("/proc/self/ns/pid").st_ino
        host_uts = os.stat("/proc/self/ns/uts").st_ino
        host_ipc = os.stat("/proc/self/ns/ipc").st_ino
        probe = f'''import ctypes, errno, hashlib, json, os, socket, subprocess, sys
def require(value):
    if not value: raise SystemExit(81)
require(os.path.isfile("/input/readonly"))
require(not os.path.exists({str(canary)!r}))
require(not os.path.exists("/run/credentials"))
require(not os.path.exists("/var/run/docker.sock"))
require(not os.path.exists("/home"))
environment = dict(os.environ)
if environment.get("LC_CTYPE") == "C.UTF-8": del environment["LC_CTYPE"]
require(environment == {{"HOME":"/work", "LANG":"C.UTF-8", "PWD":"/work"}})
require(os.stat("/proc/self/ns/net").st_ino != {host_net})
require(os.stat("/proc/self/ns/pid").st_ino != {host_pid})
require(os.stat("/proc/self/ns/uts").st_ino != {host_uts})
require(os.stat("/proc/self/ns/ipc").st_ino != {host_ipc})
require([name for _, name in socket.if_nameindex()] == ["lo"])
status = open("/proc/self/status").read()
require(status.split("CapEff:")[1].splitlines()[0].strip() == "0000000000000000")
try:
    open("/input/readonly", "w").write("not allowed")
    raise SystemExit(82)
except OSError as error:
    require(error.errno == errno.EROFS)
client = socket.socket()
client.settimeout(0.2)
try:
    client.connect(("127.0.0.1", {port}))
    raise SystemExit(83)
except (ConnectionRefusedError, TimeoutError, OSError):
    pass
finally:
    client.close()
require(len([p for p in os.listdir("/proc") if p.isdigit()]) <= 4)
open("/work/scratch", "w").write("ephemeral")
libc = ctypes.CDLL(None, use_errno=True)
for syscall in (101, 298, 310, 311, 312, 321, 438):
    ctypes.set_errno(0)
    result = libc.syscall(syscall, -1, 0, 0, 0, 0, 0)
    require(result == -1 and ctypes.get_errno() == errno.EPERM)
open("/work/supervisor-only", "w").write("invented private supervisor data")
outer_pidns = os.stat("/proc/self/ns/pid").st_ino
inner_code = "import os,sys\\nif os.path.exists('/work/supervisor-only') or os.path.exists('/output') or os.stat('/proc/self/ns/pid').st_ino == " + str(outer_pidns) + ":sys.exit(91)\\nfor fd in os.listdir('/proc/self/fd'):\\n try: target=os.readlink('/proc/self/fd/'+fd)\\n except OSError: continue\\n if 'memfd:' in target or 'artifacts' in target: sys.exit(92)\\n"
inner = ["/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--disable-userns", "--die-with-parent", "--new-session", "--clearenv", "--cap-drop", "ALL", "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/work", "/usr/bin/python3", "-I", "-S", "-c", inner_code]
require(subprocess.run(inner, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, timeout=5).returncode == 0)
for name in ("server", "frontend.tar", "verification.json"):
    with open("/output/" + name, "wb") as output: output.write(b"synthetic artifact octets")
names = ("server", "frontend.tar", "verification.json")
records = [{{"name":name,"bytes":25,"sha256":hashlib.sha256(b"synthetic artifact octets").hexdigest()}} for name in names]
with open("/output/channel", "wb") as channel:
    channel.write(json.dumps({{"artifacts":records}},separators=(",",":")).encode()+b"\\n")
    for name in names:
        with open("/output/" + name, "rb") as source:
            channel.write(source.read())
'''
        (source / "probe.py").write_text(probe)
        # Derive flags from the actual worker command; only fixture runtime roots
        # replace absent /nix/store roots, explicitly recorded in the receipt.
        configuration = {"schema_version": 1, "rules_revision": "1" * 40, "validator_store": "/nix/store/" + "a" * 32 + "-fixture",
                         "bubblewrap_store": "/nix/store/" + "b" * 32 + "-bubblewrap", "closure_file": "/nix/store/" + "c" * 32 + "-closure/store-paths"}
        outputs = {name: os.memfd_create("synthetic-output", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING) for name, _ in worker.ARTIFACTS}
        def make_command(channel, seccomp):
            production = worker.command(configuration, [configuration["validator_store"]], worker.INPUT_ROOT / ("1" * 64), channel=channel, seccomp=seccomp)
            arguments = [str(BWRAP), *production[1:]]
            source_index = arguments.index(str(worker.INPUT_ROOT / ("1" * 64)))
            arguments[source_index] = str(source)
            final_bind = arguments.index(configuration["validator_store"])
            require(arguments[final_bind - 1] == "--ro-bind", "WORKER_COMMAND_CHANGED")
            del arguments[final_bind - 1: final_bind + 2]
            arguments[-2:] = ["/usr/bin/python3", "-I", "-S", "/input/probe.py"]
            arguments[1:1] = ["--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64"]
            return arguments
        try:
            require(worker.run_with_artifacts(make_command, outputs, timeout=10), "NAMESPACE_BOUNDARY_FAILED")
            artifacts = worker.seal_artifacts(outputs)
            require(all(item["sha256"] == hashlib.sha256(b"synthetic artifact octets").hexdigest() for item in artifacts), "ARTIFACT_MISMATCH")
        finally:
            for fd in outputs.values(): os.close(fd)
        checks.update({"source_readable": True, "host_canary_inaccessible": True, "credentials_and_docker_socket_absent": True,
                       "environment_cleared": True, "network_pid_uts_ipc_namespaces_distinct": True, "host_loopback_unreachable": True,
                       "effective_capabilities_zero": True, "input_mount_readonly": True, "pid_visibility_limited": True,
                       "scratch_ephemeral": not (source_parent / "scratch").exists(), "debugger_cross_process_syscalls_refused": True,
                       "inner_candidate_cannot_see_supervisor_pid_workspace_or_outputs": True,
                       "artifacts_collected_and_sealed_outside_namespaces": True})
        try:
            connection, _ = listener.accept()
            connection.close()
            raise RuntimeError("HOST_NETWORK_ACCESSED")
        except TimeoutError:
            pass
        (source / "probe.py").write_text('import os,time\npid=os.fork()\nif pid==0:\n os.setsid()\n time.sleep(60)\nelse:\n time.sleep(60)\n')
        command = make_command(None, None)
        started = time.monotonic()
        try:
            worker.execute(command, timeout=1)
            raise RuntimeError("TIMEOUT_NOT_ENFORCED")
        except worker.Refused as error:
            require(str(error) == "VALIDATION_TIMEOUT", "UNEXPECTED_TIMEOUT_CODE")
        require(time.monotonic() - started < 7, "TIMEOUT_UNBOUNDED")
        deadline = time.monotonic() + 3
        while True:
            try:
                child, _ = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if child == 0:
                require(time.monotonic() < deadline, "DETACHED_DESCENDANT_SURVIVED")
                time.sleep(0.05)
        checks["timeout_kills_detached_descendants"] = True
        print(json.dumps({"decision": "passed", "checks": checks, "bubblewrap_version": "0.12.0", "bubblewrap_sha256": BWRAP_SHA256,
                          "worker_sha256": hashlib.sha256((ROOT / "worker.py").read_bytes()).hexdigest(),
                          "scope": "rootless host synthetic namespace probe; no production data", "limitations": [
                              "Uses pinned host Bubblewrap build and host Python runtime roots; not the NixOS service artifact",
                              "Nix-container namespace creation was refused; no privilege/seccomp bypass used",
                              "Host test does not prove VPS namespaces, cgroups, quota or CI headroom",
                              "No Forgejo runner registration or production authority established"]}, sort_keys=True))
        return 0
    finally:
        listener.close()
        shutil.rmtree(source_parent)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"decision": "failed", "code": str(error) if type(error) is RuntimeError else "QUALIFICATION_FAILED"}))
        raise SystemExit(1)
