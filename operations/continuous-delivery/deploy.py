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
import tempfile
import time

from ci import api

STATE = Path("/var/lib/mrjam-delivery")
BOOT_READY = Path("/run/mrjam-delivery-restored")
NGINX_CONF = STATE / "nginx-current.conf"
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


def slot_command(slot):
    value = command(["systemctl", "show", "mrjam-rust-" + slot + ".service", "-p", "ExecStart", "--value"])
    match = re.search(r"argv\[\]=(.*?) ; ignore_errors=", value)
    if not match or not re.fullmatch(r"/nix/store/[^ ;]+/bin/mrjam-server serve --config /nix/store/[^ ;]+/runtime.json", match[1]):
        raise RuntimeError("Cannot retain the current slot command")
    return match[1]


def configure_slot(slot, executable):
    directory = Path("/etc/systemd/system.control", "mrjam-rust-" + slot + ".service.d")
    directory.mkdir(exist_ok=True)
    temporary = directory / "90-continuous-delivery.conf.new"
    temporary.write_text("[Service]\nExecStart=\nExecStart=" + executable + "\n")
    os.replace(temporary, directory / "90-continuous-delivery.conf")
    command(["systemctl", "daemon-reload"])


def recover_preparation(restart=True):
    path = STATE / "preparation.json"
    if not path.exists():
        return
    pending = json.loads(path.read_text())
    current = STATE / "current.json"
    if current.exists() and json.loads(current.read_text())["revision"] == pending["revision"]:
        path.unlink()
        return
    configure_slot(pending["slot"], pending["command"])
    if restart:
        command(["systemctl", "restart", "mrjam-rust-" + pending["slot"] + ".service"], timeout=40)
    path.unlink()


def probe(slot, route="/readyz"):
    connection = http.client.HTTPConnection("127.0.0.1", PORTS[slot], timeout=0.8)
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
    if transaction.get("format") == 2:
        import system_delivery
        return system_delivery.rollback(transaction, reload=reload)
    atomic_json(STATE / "transaction.json", transaction)
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
    if transaction.get("replaced_slot"):
        saved = transaction["replaced_slot"]
        configure_slot(saved["slot"], saved["command"])
        if reload:
            command(["systemctl", "restart", "mrjam-rust-" + saved["slot"] + ".service"], timeout=40)
    (STATE / "transaction.json").unlink(missing_ok=True)
    print(json.dumps({"event": "rollback", "revision": transaction["revision"],
                      "seconds": round(time.monotonic() - started, 3)}), flush=True)


def recover(reload=True):
    pending = STATE / "transaction.json"
    if pending.exists():
        rollback(json.loads(pending.read_text()), reload=reload)
    recover_preparation(restart=reload)


def restore():
    if (STATE / "manual-recovery.json").exists():
        raise RuntimeError("Explicit data recovery is pending")
    recover(reload=False)
    current = STATE / "current.json"
    if current.exists():
        symlink(json.loads(current.read_text())["configuration"], NGINX_CONF)
    import system_delivery
    system_delivery.ensure_gateway_entry()
    BOOT_READY.touch()


def public_check():
    # Verify the real gateway and TLS certificate without reading response bodies.
    for host, path in [("vision.mrj.am", "/"), ("principiipetit.io", "/matheval/")]:
        deadline = time.monotonic() + 2
        while True:
            try:
                headers = command(["curl", "--silent", "--show-error", "--fail", "--max-time", "0.5",
                                   "--resolve", host + ":443:127.0.0.1", "--dump-header", "-",
                                   "--output", "/dev/null", "https://" + host + path], timeout=1)
                if "x-mrjam-source: vps-infrastructure" in headers.lower():
                    break
            except (OSError, subprocess.SubprocessError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Public gateway did not reach the candidate")
            # HUP returns before Nginx's new workers accept connections.
            time.sleep(0.05)


def candidate_configuration(old, new):
    effective = command(["systemctl", "show", "mrjam-rust-" + old + ".service",
                         "-p", "ExecStart", "--value"])
    match = re.search(r"serve --config (/nix/store/[^ ;]+/runtime.json)", effective)
    if not match:
        raise RuntimeError("Runtime configuration not found")
    # Preserve the serving configuration, including its exact frontend assets.
    # Only credential paths depend on the systemd slot; ports are unit environment.
    source = Path(match[1]).read_text()
    candidate = source.replace("/run/credentials/mrjam-rust-" + old + ".service/",
                               "/run/credentials/mrjam-rust-" + new + ".service/")
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary, "mrjam-runtime-" + new)
        directory.mkdir(mode=0o755)
        (directory / "runtime.json").write_text(candidate)
        output = command(["nix-store", "--add", str(directory)])
    symlink(output, Path("/nix/var/nix/gcroots/mrjam-runtime-" + new))
    return output + "/runtime.json"


def promote(build):
    if build.get("format") == 2:
        import system_delivery
        output = system_delivery.store_path(build["output"])
        manifest = json.loads((output / "release.json").read_text())
        if manifest.get("revision") != build["revision"] or manifest.get("format") != 2:
            raise ValueError("Release manifest mismatch")
        engine = system_delivery.store_path(manifest["engine"])
        script = engine / "operations/continuous-delivery/deploy.py"
        if script.resolve() != Path(__file__).resolve():
            # The tested candidate supplies its own deployment implementation,
            # so evolving the engine never needs a separate administrator install.
            record = STATE / ("apply-" + build["revision"] + ".json")
            atomic_json(record, build)
            record.chmod(0o600)
            try:
                result = command([str(engine / "bin/mrjam-delivery"), "apply", str(record)], timeout=1800)
                if result:
                    print(result, flush=True)
            except subprocess.CalledProcessError as error:
                if error.stdout:
                    print(error.stdout, flush=True)
                raise
            finally:
                record.unlink(missing_ok=True)
            return
        return system_delivery.promote(build)
    # Keep A available again when preparation of C fails while B is serving.
    # A durable snapshot also covers interruption before the cutover transaction.
    new = "green" if active_slot(NGINX_CONF.read_text()) == "blue" else "blue"
    snapshot = {"revision": build["revision"], "slot": new, "command": slot_command(new)}
    import system_delivery
    system_delivery.retain("retained-" + new + "-server", snapshot["command"].split("/bin/")[0])
    system_delivery.retain("retained-" + new + "-runtime", str(Path(snapshot["command"].split(" --config ")[1]).parent))
    atomic_json(STATE / "preparation.json", snapshot)
    try:
        promote_server({**build, "replaced_slot": snapshot})
    except BaseException:
        recover_preparation()
        raise
    (STATE / "preparation.json").unlink(missing_ok=True)


def promote_server(build):
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
    runtime = candidate_configuration(old, new)
    configure_slot(new, output + "/bin/mrjam-server serve --config " + runtime)
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


def refresh_engine():
    engine_script = STATE / "engine/operations/continuous-delivery/deploy.py"
    if engine_script.is_file() and engine_script.resolve() != Path(__file__).resolve():
        command(["systemctl", "restart", "--no-block", "mrjam-delivery.service"])
        return True
    return False


def watch():
    STATE.mkdir(exist_ok=True)
    with (STATE / "delivery.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        recover()
        failures = 0
        next_poll = 0
        while True:
            if (STATE / "manual-recovery.json").exists():
                time.sleep(1)
                continue
            current = STATE / "current.json"
            if current.exists():
                state = json.loads(current.read_text())
                failures = 0 if probe(state["slot"]) else failures + 1
                if failures >= 2:
                    transaction = state.get("rollback") or {"revision": state["revision"],
                              "old_configuration": state["previous_configuration"],
                              "old_state": state["previous_state"],
                              "replaced_slot": state.get("replaced_slot")}
                    try:
                        rollback(transaction)
                    except Exception:
                        if not (STATE / "manual-recovery.json").exists():
                            raise
                    if refresh_engine():
                        return
                    failures = 0
            if time.monotonic() >= next_poll:
                next_poll = time.monotonic() + 10
                build = None
                try:
                    build = next_build()
                    if build:
                        promote(build)
                        # Activation installs the engine from the exact tested
                        # source. Replace this process only after its transaction.
                        if refresh_engine():
                            return
                except Exception as error:
                    if build:
                        record_failure(build["revision"])
                    detail = {"event": "delivery-check-failed", "error": type(error).__name__}
                    if isinstance(error, (RuntimeError, ValueError)):
                        detail["reason"] = str(error)
                    if isinstance(error, subprocess.CalledProcessError):
                        detail.update(command=Path(error.cmd[0]).name, returncode=error.returncode)
                    print(json.dumps(detail), flush=True)
            time.sleep(1)


if __name__ == "__main__":
    if sys.argv[1] == "apply" and len(sys.argv) == 3:
        path = Path(sys.argv[2]).resolve(strict=True)
        if path.parent != STATE.resolve() or not re.fullmatch(r"apply-[0-9a-f]{40}\.json", path.name):
            raise ValueError("Expected the coordinator-owned application record")
        import system_delivery
        try:
            system_delivery.promote(json.loads(path.read_text()))
        except Exception as error:
            detail = {"event": "application-failed", "error": type(error).__name__}
            if isinstance(error, (RuntimeError, ValueError)):
                detail["reason"] = str(error)
            if isinstance(error, subprocess.CalledProcessError):
                detail.update(command=Path(error.cmd[0]).name, returncode=error.returncode)
            print(json.dumps(detail), flush=True)
            raise
    else:
        {"watch": watch, "recover": recover, "restore": restore}[sys.argv[1]]()
