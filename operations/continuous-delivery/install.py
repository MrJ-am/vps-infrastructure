#!/usr/bin/env python3
"""Install the standard runner and main delivery services from built Nix paths.

Run on the VPS as administrator. Credentials remain local and are never printed.
No application is restarted and no database is opened by this installer.
"""
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def run(arguments):
    return subprocess.run(arguments, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True).stdout.strip()


def request(method, path, body=None):
    token = Path("/etc/mrjam-ci/admin-token").read_text().strip()
    c = http.client.HTTPConnection("127.0.0.1", 3004, timeout=30)
    try:
        c.request(method, "/api/v1/" + path, body=json.dumps(body) if body is not None else None,
                  headers={"Authorization": "token " + token, "Host": "forge.mrj.am",
                           "Content-Type": "application/json"})
        r = c.getresponse()
        raw = r.read()
        if r.status not in (200, 201, 204):
            raise RuntimeError(method + " " + path + " HTTP " + str(r.status))
        return json.loads(raw) if raw else None
    finally:
        c.close()


def secret(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "w") as stream:
        stream.write(value + "\n")


def main():
    if os.getuid() != 0 or len(sys.argv) != 3:
        raise ValueError("Usage: install.py PACKAGE SERVICES (administrator only)")
    package, services = map(Path, sys.argv[1:])
    for path in [package, services]:
        if not re.fullmatch(r"/nix/store/[0-9a-z]{32}-[A-Za-z0-9+._-]+", str(path)):
            raise ValueError("Expected a built Nix store path")
    config = Path("/etc/mrjam-ci")
    config.mkdir(mode=0o755, exist_ok=True)
    state = Path("/var/lib/mrjam-delivery")
    state.mkdir(mode=0o755, exist_ok=True)
    if not (config / "admin-token").exists():
        token = run(["runuser", "-u", "forgejo", "--",
                     "/nix/store/qcrq6ngi273hak8l7ldv1k9zqq0cqg2h-forgejo-17.0.1/bin/forgejo",
                     "--config", "/run/mrjam-forgejo/app.ini", "admin", "user", "generate-access-token",
                     "--username", "MrJam", "--token-name", "mrjam-ci-installation-20261104",
                     "--scopes", "write:repository", "--raw"])
        if not re.fullmatch(r"[0-9a-f]{40}", token):
            raise RuntimeError("Unexpected generated administrative credential format")
        secret(config / "admin-token", token)
    base = "repos/MrJ-am/vps-infrastructure"
    before = state / "forgejo-before.json"
    if not before.exists():
        repo = request("GET", base)
        protection = request("GET", base + "/branch_protections/main")
        before.write_text(json.dumps({"has_actions": repo["has_actions"], "protection": protection}) + "\n")
    if not (config / "source-token").exists():
        token = run(["runuser", "-u", "forgejo", "--",
                     "/nix/store/qcrq6ngi273hak8l7ldv1k9zqq0cqg2h-forgejo-17.0.1/bin/forgejo",
                     "--config", "/run/mrjam-forgejo/app.ini", "admin", "user", "generate-access-token",
                     "--username", "mrjam-ci-policy", "--token-name", "mrjam-ci-source-20261104",
                     "--scopes", "read:repository", "--raw"])
        if not re.fullmatch(r"[0-9a-f]{40}", token):
            raise RuntimeError("Unexpected generated credential format")
        secret(config / "source-token", token)
    request("PATCH", base, {"has_actions": True})
    identity_file = config / "identity.json"
    if not identity_file.exists():
        runners = request("GET", base + "/actions/runners")
        if any(item.get("name") == "mrjam-ci" for item in runners):
            raise RuntimeError("Runner already exists without local registration; preserve it")
        registered = request("POST", base + "/actions/runners", {
            "name": "mrjam-ci", "description": "Tests and Nix builds", "ephemeral": False})
        secret(config / "runner-token", registered["token"])
        identity_file.write_text(json.dumps({k: registered[k] for k in ["id", "uuid"]}) + "\n")
    identity = json.loads(identity_file.read_text())
    connection = {
        "log": {"level": "info", "job_level": "info"},
        "runner": {"capacity": 1, "timeout": "90m", "shutdown_timeout": "90m", "envs": {},
                   "env_file": "/dev/null", "fetch_interval": "3s", "insecure": False},
        "cache": {"enabled": False},
        "container": {"docker_host": "-", "privileged": False, "valid_volumes": []},
        "host": {"workdir_parent": "/var/lib/mrjam-ci/jobs"},
        "server": {"connections": {"infrastructure": {
            "url": "http://127.0.0.1:3004", "uuid": identity["uuid"],
            "token_url": "file:$CREDENTIALS_DIRECTORY/runner-token", "labels": ["mrjam-ci:host"]}}},
    }
    (config / "runner.json").write_text(json.dumps(connection) + "\n")
    if not (state / "baseline.json").exists():
        spec = importlib.util.spec_from_file_location("ci", package / "operations/continuous-delivery/ci.py")
        ci = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ci)
        # Supply the already installed read-only source credential without copying it.
        os.environ["CREDENTIALS_DIRECTORY"] = str(config)
        with tempfile.TemporaryDirectory(prefix="baseline-", dir=state) as directory:
            root = Path(directory) / "source"
            revision = "8977c76717006f562b2ca3123ad1f3283007e568"
            ci.export("mrjam-plateforme", revision, root)
            for name, repository in [("vision", "vision"), ("mateval", "matheval")]:
                item = json.loads(ci.api("repos/MrJ-am/mrjam-plateforme/contents/components/" + name + "?ref=" + revision))
                target = root / "components" / name
                if target.exists():
                    target.rmdir()
                ci.export(repository, item["sha"], target)
            digest = ci.schema_digest(root)
        nginx_pid = run(["systemctl", "show", "nginx.service", "-p", "MainPID", "--value"])
        baseline = {"schema_digest": digest, "initial_revision": revision,
                    "initial_output": "/nix/store/s7jifv4bgzbgjddfsfq20x2vkjmvjc6x-mrjam-delivery-server-76cfaec0736c",
                    "nginx": os.readlink("/proc/" + nginx_pid + "/exe")}
        (state / "baseline.json").write_text(json.dumps(baseline) + "\n")
    roots = Path("/nix/var/nix/gcroots")
    for label, path in [("package", package), ("services", services)]:
        link = roots / ("mrjam-delivery-" + label)
        link.unlink(missing_ok=True)
        link.symlink_to(path)
    control = Path("/etc/systemd/system.control")
    # Keep the explicitly abandoned chain stopped, including after a Forgejo
    # restart or a reboot. Do not touch application workers or backup timers.
    legacy = ["mrjam-forgejo-runner.service"] + [name + ".timer" for name in [
        "mrjam-github-discovery", "mrjam-admission-controller", "mrjam-intake-prepare",
        "mrjam-acceptance-mirror", "mrjam-acceptance-review", "mrjam-acceptance-merge",
        "mrjam-acceptance-sync", "mrjam-delivery-preparation", "mrjam-delivery-staging",
        "mrjam-promotion"]]
    for name in legacy:
        dropin = control / (name + ".d")
        dropin.mkdir(exist_ok=True)
        (dropin / "90-legacy-disabled.conf").write_text(
            "[Unit]\nConditionPathExists=/etc/mrjam-legacy-delivery-enabled\n")
    wanted = control / "multi-user.target.wants"
    wanted.mkdir(exist_ok=True)
    for name in ["mrjam-ci", "mrjam-delivery", "mrjam-delivery-restore"]:
        unit = control / (name + ".service")
        if unit.exists() and not unit.is_symlink():
            raise RuntimeError("Existing unmanaged service: " + name)
        unit.unlink(missing_ok=True)
        unit.symlink_to(services / (name + ".service"))
        wanted_link = wanted / (name + ".service")
        wanted_link.unlink(missing_ok=True)
        wanted_link.symlink_to(unit)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "start", "mrjam-ci.service", "mrjam-delivery.service"])
    print(json.dumps({"installed": True, "runner_id": identity["id"], "package": str(package),
                      "services": str(services), "application_cutover": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        detail = str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__
        if isinstance(error, OSError):
            detail += " errno=" + str(error.errno) + " path=" + str(error.filename)
        print("Installation failed: " + detail, file=sys.stderr)
        sys.exit(1)
