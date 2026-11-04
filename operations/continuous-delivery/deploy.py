#!/usr/bin/env python3
"""Deliver successful Forgejo main builds to the inactive slot, then switch Nginx."""
import fcntl
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from ci import api

STATE = Path("/var/lib/mrjam-delivery")
NGINX_CONF = Path("/etc/nginx/nginx.conf")
PORTS = {"blue": 38101, "green": 38102}
REPO = "repos/MrJ-am/vps-infrastructure"


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def symlink(target, destination):
    temporary = destination.with_name(destination.name + ".new")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, destination)


def command(arguments, timeout=30):
    return subprocess.run(arguments, check=True, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout.strip()


def probe(slot, route="/readyz"):
    connection = http.client.HTTPConnection("127.0.0.1", PORTS[slot], timeout=0.4)
    try:
        connection.request("GET", route)
        return connection.getresponse().status == 200
    except OSError:
        return False
    finally:
        connection.close()


def reload_nginx():
    command(["systemctl", "reload", "nginx.service"], timeout=3)


def active_slot(configuration):
    matches = [slot for slot, port in PORTS.items() if "127.0.0.1:" + str(port) in configuration]
    if len(matches) != 1:
        raise RuntimeError("Expected a single active upstream slot")
    return matches[0]


def switched(configuration, old, new):
    return configuration.replace("127.0.0.1:" + str(PORTS[old]), "127.0.0.1:" + str(PORTS[new]))


def record_failure(revision):
    atomic_json(STATE / "failed.json", {"revision": revision, "at": time.time()})


def rollback(transaction, reload=True):
    started = time.monotonic()
    symlink(transaction["old_configuration"], NGINX_CONF)
    if reload:
        reload_nginx()
    old = transaction.get("old_state")
    if old:
        atomic_json(STATE / "current.json", old)
    else:
        (STATE / "current.json").unlink(missing_ok=True)
    record_failure(transaction["revision"])
    (STATE / "transaction.json").unlink(missing_ok=True)
    print(json.dumps({"event": "rollback", "revision": transaction["revision"],
                      "seconds": round(time.monotonic() - started, 3)}), flush=True)


def recover(reload=True):
    pending = STATE / "transaction.json"
    if pending.exists():
        rollback(json.loads(pending.read_text()), reload=reload)


def restore():
    recover(reload=False)
    current = STATE / "current.json"
    if current.exists():
        symlink(json.loads(current.read_text())["configuration"], NGINX_CONF)


def public_check():
    # Verify the real gateway and TLS certificate without reading response bodies.
    for host, path in [("vision.mrj.am", "/"), ("principiipetit.io", "/matheval/")]:
        headers = command(["curl", "--silent", "--show-error", "--fail", "--max-time", "1",
                           "--resolve", host + ":443:127.0.0.1", "--dump-header", "-",
                           "--output", "/dev/null", "https://" + host + path], timeout=2)
        if "x-mrjam-source: vps-infrastructure" not in headers.lower():
            raise RuntimeError("Public gateway did not reach the candidate")


def promote(build):
    revision, output = build["revision"], build["output"]
    if not re.fullmatch(r"/nix/store/[0-9a-z]{32}-[A-Za-z0-9+._-]+", output):
        raise ValueError("Invalid artifact path")
    if Path(output, "share/mrjam/source-revision").read_text().strip() != revision:
        raise ValueError("Artifact revision mismatch")
    baseline = json.loads((STATE / "baseline.json").read_text())
    if build["schema_digest"] != baseline["schema_digest"]:
        raise RuntimeError("Schema change requires the separate migration procedure")
    symlink(output, Path("/nix/var/nix/gcroots/mrjam-delivery-candidate"))
    configuration = NGINX_CONF.read_text()
    old = active_slot(configuration)
    new = "green" if old == "blue" else "blue"
    if not probe(old):
        raise RuntimeError("Current version is not ready")
    unit = "mrjam-rust-" + new + ".service"
    effective = command(["systemctl", "show", unit, "-p", "ExecStart", "--value"])
    match = re.search(r"serve --config (/nix/store/[^ ;]+/runtime.json)", effective)
    if not match:
        raise RuntimeError("Runtime configuration not found")
    directory = Path("/etc/systemd/system.control", unit + ".d")
    directory.mkdir(exist_ok=True)
    override = directory / "90-continuous-delivery.conf"
    override.write_text("[Service]\nExecStart=\nExecStart=" + output
                        + "/bin/mrjam-server serve --config " + match[1] + "\n")
    command(["systemctl", "daemon-reload"])
    command(["systemctl", "restart", unit], timeout=40)
    deadline = time.monotonic() + 30
    while not (probe(new, "/healthz") and probe(new)):
        if time.monotonic() >= deadline:
            raise RuntimeError("Candidate did not become ready; traffic unchanged")
        time.sleep(0.5)
    # Everything slow has completed. Both slots remain running.
    next_configuration = STATE / ("nginx-" + revision + ".conf")
    next_configuration.write_text(switched(configuration, old, new))
    next_configuration.chmod(0o644)
    nginx = baseline["nginx"]
    command([nginx, "-t", "-c", str(next_configuration)])
    current_file = STATE / "current.json"
    old_state = json.loads(current_file.read_text()) if current_file.exists() else None
    transaction = {"revision": revision, "old_slot": old, "new_slot": new,
                   "old_configuration": str(NGINX_CONF.resolve()), "old_state": old_state}
    atomic_json(STATE / "transaction.json", transaction)
    started = time.monotonic()
    try:
        symlink(next_configuration, NGINX_CONF)
        reload_nginx()
        if not (probe(new) and probe(old)):
            raise RuntimeError("Immediate readiness check failed")
        public_check()
        atomic_json(current_file, {**build, "slot": new, "previous_slot": old,
                                   "configuration": str(next_configuration),
                                   "previous_configuration": transaction["old_configuration"],
                                   "previous_state": old_state,
                                   "cutover_seconds": round(time.monotonic() - started, 3)})
        (STATE / "transaction.json").unlink()
        for label, target in [("current", output), ("previous", baseline["initial_output"] if old_state is None else old_state["output"])]:
            symlink(target, Path("/nix/var/nix/gcroots/mrjam-delivery-" + label))
        print(json.dumps({"event": "deployed", "revision": revision, "slot": new,
                          "seconds": round(time.monotonic() - started, 3)}), flush=True)
    except BaseException:
        rollback(transaction)
        raise


def next_build():
    branch = json.loads(api(REPO + "/branches/main", timeout=1))
    revision = branch["commit"]["id"]
    for filename in ["current.json", "failed.json"]:
        path = STATE / filename
        if path.exists() and json.loads(path.read_text())["revision"] == revision:
            return None
    runs = json.loads(api(REPO + "/actions/runs?branch=main&limit=20", timeout=1))
    if not any(run.get("commit_sha") == revision and run.get("status") == "success"
               and run.get("trigger_event") == "push" and run.get("workflow_id") == "ci.yml"
               and run.get("prettyref") == "main"
               for run in runs.get("workflow_runs", [])):
        return None
    result = Path("/var/lib/mrjam-ci/results", revision + ".json")
    if result.exists():
        build = json.loads(result.read_text())
        if build["revision"] == revision:
            return build
    return None


def watch():
    STATE.mkdir(exist_ok=True)
    with (STATE / "delivery.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        recover()
        failures = 0
        next_poll = 0
        while True:
            current = STATE / "current.json"
            if current.exists():
                state = json.loads(current.read_text())
                failures = 0 if probe(state["slot"]) else failures + 1
                if failures >= 2:
                    rollback({"revision": state["revision"],
                              "old_configuration": state["previous_configuration"],
                              "old_state": state["previous_state"]})
                    failures = 0
            if time.monotonic() >= next_poll:
                next_poll = time.monotonic() + 10
                build = None
                try:
                    build = next_build()
                    if build:
                        promote(build)
                except Exception as error:
                    if build:
                        record_failure(build["revision"])
                    print("Delivery check failed: " + type(error).__name__, flush=True)
            time.sleep(1)


if __name__ == "__main__":
    {"watch": watch, "recover": recover, "restore": restore}[sys.argv[1]]()
