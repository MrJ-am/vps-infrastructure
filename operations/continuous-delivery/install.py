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
    if os.getuid() != 0 or len(sys.argv) not in (3, 4) or (len(sys.argv) == 4 and sys.argv[3] != "--ci-only"):
        raise ValueError("Usage: install.py PACKAGE SERVICES [--ci-only] (administrator only)")
    ci_only = len(sys.argv) == 4
    package, services = map(Path, sys.argv[1:3])
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
    protection = request("GET", base + "/branch_protections/main")
    desired = {key: value for key, value in protection.items()
               if key not in ["branch_name", "rule_name", "created_at", "updated_at"]}
    desired["status_check_contexts"] = ["Tests et construction / tests*"]
    desired["required_approvals"] = 0
    request("PATCH", base + "/branch_protections/main", desired)
    actual = request("GET", base + "/branch_protections/main")
    if any(actual.get(key) != value for key, value in desired.items()):
        raise RuntimeError("Forgejo branch protection recheck failed")
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
    engine = config / "engine"
    temporary_engine = config / "engine.new"
    temporary_engine.unlink(missing_ok=True)
    temporary_engine.symlink_to(package)
    os.replace(temporary_engine, engine)
    stable_engine = state / "engine"
    next_stable = state / "engine.new"
    next_stable.unlink(missing_ok=True)
    next_stable.symlink_to(package)
    os.replace(next_stable, stable_engine)
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
    previous_controls = Path("/etc/systemd/system.control/mrjam-delivery.service")
    retained_controls = roots / "mrjam-delivery-initial-controls"
    if previous_controls.is_symlink() and not retained_controls.exists():
        retained_controls.symlink_to(previous_controls.resolve().parent)
    retained_system = roots / "mrjam-delivery-initial-system"
    if not retained_system.exists():
        retained_system.symlink_to(Path("/run/current-system").resolve())
    baseline_path = state / "baseline.json"
    metadata = json.loads(baseline_path.read_text())
    if "stateful_versions" not in metadata:
        expression = ("let b=(import " + str(package / "operations/continuous-delivery/installed-baseline.nix")
                      + " {}).evaluate []; lib=(import " + str(package / "operations/forgejo/locked-toolchain.nix")
                      + " {}).lib; in { postgresql=b.services.postgresql.package.version; "
                      + "forgejo=lib.getVersion b.services.mrjamForgejoHost.artifactStorePath; "
                      + "kanidm=lib.getVersion b.services.mrjamKanidmHost.artifactStorePath; "
                      + "nextcloud=b.services.nextcloud.package.version; }")
        metadata["stateful_versions"] = json.loads(run(["nix-instantiate", "--read-write-mode", "--eval",
                                                        "--strict", "--json", "--expr", expression]))
        spec = importlib.util.spec_from_file_location("ci", package / "operations/continuous-delivery/ci.py")
        ci = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ci)
        os.environ["CREDENTIALS_DIRECTORY"] = str(config)
        value = run(["systemctl", "show", "vise.service", "-p", "ExecStart", "--value"])
        match = re.search(r"path=(/nix/store/[^ ;]+)/server", value)
        if not match:
            raise RuntimeError("Installed ViSe artifact not found")
        revision = json.loads(Path(match[1], "artifact.json").read_text())["revision"]
        with tempfile.TemporaryDirectory(prefix="schema-baseline-", dir=state) as directory:
            root = Path(directory) / "source"
            ci.export("etp-vie-affective", revision, root)
            metadata["schema_digests"] = {"server": metadata["schema_digest"],
                                          "vise": ci.schema_digest(root / "backend")}
        next_metadata = state / "baseline.next"
        next_metadata.write_text(json.dumps(metadata) + "\n")
        os.replace(next_metadata, baseline_path)
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
    for name in (["mrjam-ci"] if ci_only else ["mrjam-ci", "mrjam-delivery", "mrjam-delivery-restore"]):
        unit = control / (name + ".service")
        if unit.exists() and not unit.is_symlink():
            raise RuntimeError("Existing unmanaged service: " + name)
        unit.unlink(missing_ok=True)
        unit.symlink_to(services / (name + ".service"))
        wanted_link = wanted / (name + ".service")
        wanted_link.unlink(missing_ok=True)
        wanted_link.symlink_to(unit)
    run(["systemctl", "daemon-reload"])
    if not ci_only:
        gateway = state / "nginx-current.conf"
        primary = Path("/etc/nginx/nginx.conf")
        if not gateway.exists():
            gateway.symlink_to(primary.resolve())
        entry = state / "nginx-entry.conf"
        entry.write_text("include " + str(gateway) + ";\n")
        entry.chmod(0o644)
        next_primary = primary.with_suffix(".next")
        next_primary.unlink(missing_ok=True)
        next_primary.symlink_to(entry)
        os.replace(next_primary, primary)
        run(["systemctl", "reload", "nginx.service"])
        # These persist across return to a pre-bootstrap system generation.
        for name in ["nginx", "postgresql", "forgejo", "kanidm", "mrjam-identity", "mrjam-identity-deletion",
                     "mrjam-rust-blue", "mrjam-rust-green", "vise", "phpfpm-nextcloud",
                     "mrjam-vision-archive", "mrjam-vision-cycle", "mrjam-vision-replay",
                     "mrjam-vision-admission", "mrjam-vision-closure"]:
            directory = control / (name + ".service.d")
            directory.mkdir(exist_ok=True)
            (directory / "10-delivery-recovery.conf").write_text(
                "[Unit]\nAfter=mrjam-delivery-restore.service\nConditionPathExists=/run/mrjam-delivery-restored\n")
        run(["systemctl", "daemon-reload"])
        if not Path("/run/mrjam-delivery-restored").exists():
            run(["systemctl", "restart", "mrjam-delivery-restore.service"])
        run(["systemctl", "start", "mrjam-delivery-restore.service", "mrjam-delivery.service"])
    run(["systemctl", "start", "mrjam-ci.service"])
    print(json.dumps({"installed": True, "runner_id": identity["id"], "package": str(package),
                      "services": str(services), "ci_only": ci_only, "application_cutover": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        detail = str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__
        if isinstance(error, OSError):
            detail += " errno=" + str(error.errno) + " path=" + str(error.filename)
        print("Installation failed: " + detail, file=sys.stderr)
        sys.exit(1)
