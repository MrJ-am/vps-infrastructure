#!/usr/bin/env python3
"""Real Forgejo 17.0.1, entirely disposable SQLite/loopback fixture.

Requires the existing pinned local Nix container with --network none. No host
user database is edited, no persistent application directory is mounted, and
all invented identities/tokens/repos are discarded. Only closed results leave.
"""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

FORGEJO = "/nix/store/qcrq6ngi273hak8l7ldv1k9zqq0cqg2h-forgejo-17.0.1/bin/forgejo"
RUNNER = "/nix/store/f767py3j9434ds3ldcwdgxjr4ksz9y8a-forgejo-runner-13.2.0/bin/forgejo-runner"
GIT = "/nix/store/gy266y3ax8xvblz36m6an7h8mi485mf1-git-2.54.0/bin"
SWAGGER = "/nix/store/bcjp3pf5gldhjcgk752293h6x8ipgfzi-forgejo-17.0.1-data/templates/swagger/v1_json.tmpl"
ROOT = Path(__file__).resolve().parents[1]
PORT = 38173
ORIGIN = "http://127.0.0.1:" + str(PORT)
spec = importlib.util.spec_from_file_location("reconcile", ROOT / "reconcile.py")
reconcile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconcile)
registration_spec = importlib.util.spec_from_file_location("register_runner", ROOT / "register_runner.py")
registration = importlib.util.module_from_spec(registration_spec)
registration_spec.loader.exec_module(registration)


def require(value, code):
    if not value:
        raise RuntimeError(code)


def main():
    require(os.getuid() == 0 and os.environ.get("MRJAM_SYNTHETIC_CONTAINER") == "1", "SYNTHETIC_CONTAINER_REQUIRED")
    require(set(os.listdir("/sys/class/net")) == {"lo"}, "OFFLINE_LOOPBACK_REQUIRED")
    require(Path(FORGEJO).is_file(), "PINNED_FORGEJO_REQUIRED")
    user = pwd.getpwnam("nobody")
    require(user.pw_uid == 65534 and user.pw_gid == 65534, "SYNTHETIC_IDENTITY_REQUIRED")
    parent = Path(tempfile.mkdtemp(prefix="mrjam-forgejo-synthetic-", dir="/tmp"))
    os.chown(parent, user.pw_uid, user.pw_gid)
    config = parent / "app.ini"
    config.write_text(f"""APP_NAME = Synthetic Forgejo qualification
RUN_USER = nobody
RUN_MODE = prod
WORK_PATH = {parent}
[server]
DOMAIN = 127.0.0.1
ROOT_URL = {ORIGIN}/
LOCAL_ROOT_URL = {ORIGIN}/
HTTP_ADDR = 127.0.0.1
HTTP_PORT = {PORT}
DISABLE_SSH = true
OFFLINE_MODE = true
APP_DATA_PATH = {parent}/data
[database]
DB_TYPE = sqlite3
PATH = {parent}/data/forgejo.db
[repository]
ROOT = {parent}/repositories
DEFAULT_BRANCH = main
[security]
INSTALL_LOCK = true
SECRET_KEY = SYNTHETIC_ONLY_NO_PRODUCTION_SECRET
INTERNAL_TOKEN = SYNTHETIC_ONLY_NO_PRODUCTION_TOKEN
[service]
DISABLE_REGISTRATION = true
ENABLE_BASIC_AUTHENTICATION = true
[session]
COOKIE_SECURE = false
[actions]
ENABLED = true
[mailer]
ENABLED = false
[packages]
ENABLED = false
[federation]
ENABLED = false
[log]
MODE = console
LEVEL = Fatal
""")
    os.chown(config, user.pw_uid, user.pw_gid)
    config.chmod(0o600)
    environment = {"PATH": GIT + ":/nix/var/nix/profiles/default/bin:/bin", "HOME": str(parent), "USER": "nobody", "GITEA_WORK_DIR": str(parent)}
    def demote():
        os.setsid()
        os.setgroups([])
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
    def cli(*arguments):
        result = subprocess.run([FORGEJO, "--config", str(config), "--work-path", str(parent), *arguments],
                                env=environment, cwd=parent, preexec_fn=demote, capture_output=True, timeout=40)
        require(result.returncode == 0, "SYNTHETIC_FORGEJO_CLI_FAILED")
        return result.stdout
    server = runner = runner_log = None
    checks = {}
    try:
        swagger = json.loads(Path(SWAGGER).read_text())
        desired = reconcile.desired_protection()
        require(set(desired) <= set(swagger["definitions"]["CreateBranchProtectionOption"]["properties"]), "CREATE_API_MAPPING_CHANGED")
        require(set(desired) - {"branch_name", "rule_name"} <= set(swagger["definitions"]["EditBranchProtectionOption"]["properties"]), "EDIT_API_MAPPING_CHANGED")
        checks["pinned_swagger_mapping"] = True
        cli("migrate")
        cli("admin", "user", "create", "--username", "synthetic-controller", "--password", "SYNTHETIC-ONLY-fixture-9482!", "--email", "controller@example.invalid", "--admin", "--must-change-password=false")
        token = cli("admin", "user", "generate-access-token", "--username", "synthetic-controller", "--token-name", "synthetic-only", "--scopes", "all", "--raw").decode("ascii").strip()
        require(len(token) == 40 and all(character in "0123456789abcdef" for character in token), "SYNTHETIC_TOKEN_FORMAT")
        server = subprocess.Popen([FORGEJO, "--config", str(config), "--work-path", str(parent), "web"], env=environment,
                                  cwd=parent, preexec_fn=demote, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), reconcile.NoRedirect())
        def request(method, path, body=None):
            data = None if body is None else json.dumps(body).encode("utf-8")
            req = urllib.request.Request(ORIGIN + path, data=data, method=method,
                                         headers={"Authorization": "token " + token, "Content-Type": "application/json"})
            try:
                with opener.open(req, timeout=3) as response:
                    raw = response.read(131073)
                    require(len(raw) <= 131072, "SYNTHETIC_RESPONSE_LIMIT")
                    return response.status, {} if not raw else json.loads(raw)
            except urllib.error.HTTPError as error:
                status = error.code
                error.close()
                return status, {}
        deadline = time.monotonic() + 45
        while True:
            require(server.poll() is None, "SYNTHETIC_SERVER_STOPPED")
            try:
                status, body = request("GET", "/api/v1/version")
                if status == 200:
                    require(body == {"version": "17.0.1"}, "PINNED_VERSION_CHANGED")
                    break
            except (OSError, urllib.error.URLError):
                pass
            require(time.monotonic() < deadline, "SYNTHETIC_START_TIMEOUT")
            time.sleep(0.1)
        checks["forgejo_running_as_unprivileged_user"] = True
        status, _ = request("POST", "/api/v1/orgs", {"username": "MrJ-am", "visibility": "private"})
        require(status == 201, "SYNTHETIC_ORGANIZATION_FAILED")
        policy = {"schema_version": 2, "owner": "MrJ-am", "forgejo_version": "17.0.1", "rules_revision": "1" * 40,
                  "controller_revision": "2" * 40, "phase": "bootstrap-repositories", "repositories": sorted(reconcile.REPOSITORIES)}
        consumed = set()
        def consume(value):
            require(value not in consumed, "SYNTHETIC_PLAN_REUSED")
            consumed.add(value)
        api = reconcile.Transport(token, synthetic_port=PORT)
        first = reconcile.plan(policy, reconcile.observe(api, policy))
        first_result = reconcile.apply(api, policy, first, consume=consume)
        require(first_result["operations_applied"] == len(reconcile.REPOSITORIES), "BOOTSTRAP_INCOMPLETE")
        checks["nine_private_repositories_created_actions_disabled"] = True
        before = api.requests
        repeated = reconcile.apply(api, policy, first, consume=consume)
        require(repeated["decision"] == "no-changes" and len(consumed) == 1, "BOOTSTRAP_NOT_IDEMPOTENT")
        checks["bootstrap_repeat_no_mutation"] = True
        # Synthetic code only, before protection; production import is a distinct
        # approved exact-source transfer, never part of this metadata controller.
        for name in policy["repositories"]:
            status, _ = request("POST", reconcile.path_for(name) + "/contents/README.txt", {
                "branch": "main", "message": "Synthetic source fixture", "content": base64.b64encode(b"invented fixture only\n").decode("ascii")})
            require(status == 201, "SYNTHETIC_SOURCE_SEED_FAILED")
        workflow = b'''name: Synthetic coordinator qualification\non:\n  workflow_dispatch:\njobs:\n  coordinator:\n    runs-on: mrjam-controller\n    steps:\n      - name: Fixed synthetic command\n        run: test "$MRJAM_SYNTHETIC_FIXTURE" = "only-invented-data"\n'''
        status, _ = request("POST", reconcile.path_for("mrjam-validation") + "/contents/.forgejo/workflows/synthetic.yml", {
            "branch": "main", "message": "Synthetic workflow fixture", "content": base64.b64encode(workflow).decode("ascii")})
        require(status == 201, "SYNTHETIC_WORKFLOW_SEED_FAILED")
        # Preserve a public repository's visibility while adopting protections.
        status, _ = request("PATCH", reconcile.path_for("Signature"), {"private": False})
        require(status == 200, "SYNTHETIC_VISIBILITY_SETUP_FAILED")
        policy["phase"] = "protect-main"
        api = reconcile.Transport(token, synthetic_port=PORT)
        second = reconcile.plan(policy, reconcile.observe(api, policy))
        second_result = reconcile.apply(api, policy, second, consume=consume)
        require(second_result["operations_applied"] == len(reconcile.REPOSITORIES), "PROTECTION_INCOMPLETE")
        checks["nine_main_protections_applied_and_read_back"] = True
        api = reconcile.Transport(token, synthetic_port=PORT)
        repeated = reconcile.apply(api, policy, second, consume=consume)
        require(repeated["decision"] == "no-changes" and len(consumed) == 2, "PROTECTION_NOT_IDEMPOTENT")
        checks["protection_repeat_no_mutation"] = True
        require(reconcile.observe_repository(api, "Signature")["private"] is False, "EXISTING_VISIBILITY_CHANGED")
        checks["existing_public_visibility_preserved"] = True
        status, _ = request("POST", reconcile.path_for("mrjam-plateforme") + "/contents/forbidden.txt", {
            "branch": "main", "message": "Must be refused", "content": base64.b64encode(b"synthetic forbidden write\n").decode("ascii")})
        require(status in (403, 405), "PROTECTED_MAIN_DIRECT_WRITE_NOT_REFUSED")
        checks["direct_write_to_main_refused_even_for_admin"] = True
        status, _ = request("DELETE", reconcile.path_for("mrjam-plateforme") + "/branches/main")
        require(status in (403, 405), "PROTECTED_MAIN_DELETION_NOT_REFUSED")
        checks["protected_main_deletion_refused"] = True
        # Exercise the repository-scoped registration API and the actual pinned
        # daemon. This fixture's job is a fixed shell test, not candidate code.
        status, branch = request("GET", reconcile.path_for("mrjam-validation") + "/branches/main")
        require(status == 200, "SYNTHETIC_BRANCH_UNAVAILABLE")
        rules = branch["commit"]["id"]
        policy["phase"] = "operate-validation"
        policy["rules_revision"] = rules
        api = reconcile.Transport(token, synthetic_port=PORT)
        operations = reconcile.plan(policy, reconcile.observe(api, policy))
        enabled = reconcile.apply(api, policy, operations, consume=consume)
        require(enabled["operations_applied"] == 1, "SYNTHETIC_ACTIONS_ENABLE_FAILED")
        checks["actions_enabled_only_after_pinned_main_protection"] = True
        saved = []
        registrar = registration.Transport(token, synthetic_port=PORT)
        registered = registration.register(registrar, {"rules_revision": rules}, None, lambda metadata, secret: saved.append((metadata, secret)))
        require(registered["decision"] == "registered" and len(saved) == 1, "SYNTHETIC_REGISTRATION_FAILED")
        repeated = registration.register(registrar, {"rules_revision": rules}, saved[0][0], lambda *_: require(False, "UNEXPECTED_REGISTRATION_MUTATION"))
        require(repeated["decision"] == "no-changes", "REGISTRATION_NOT_IDEMPOTENT")
        checks["repository_scoped_registration_and_idempotence"] = True
        credential_dir = parent / "synthetic-credentials"
        credential_dir.mkdir(mode=0o700)
        os.chown(credential_dir, user.pw_uid, user.pw_gid)
        credential = credential_dir / "runner-token"
        credential.write_text(saved[0][1] + "\n")
        credential.chmod(0o400)
        os.chown(credential, user.pw_uid, user.pw_gid)
        runner_config = registration.configuration(saved[0][0])
        runner_config["log"] = {"level": "debug", "job_level": "debug"}
        runner_config["server"]["connections"]["mrjam-validation"]["url"] = ORIGIN
        runner_config["host"]["workdir_parent"] = str(parent / "synthetic-jobs")
        runner_config["runner"]["envs"] = {"MRJAM_SYNTHETIC_FIXTURE": "only-invented-data"}
        runner_config["runner"]["fetch_interval"] = "1s"
        runner_config_path = parent / "runner.json"
        runner_config_path.write_text(json.dumps(runner_config))
        os.chown(runner_config_path, user.pw_uid, user.pw_gid)
        runner_log = tempfile.TemporaryFile()
        runner = subprocess.Popen([RUNNER, "daemon", "--config", str(runner_config_path)],
                                  env={**environment, "CREDENTIALS_DIRECTORY": str(credential_dir)}, cwd=parent,
                                  preexec_fn=demote, stdin=subprocess.DEVNULL, stdout=runner_log, stderr=runner_log)
        deadline = time.monotonic() + 45
        while True:
            require(runner.poll() is None, "SYNTHETIC_RUNNER_STOPPED")
            status, remote = request("GET", registration.RUNNERS + "/" + str(saved[0][0]["id"]))
            if status == 200 and remote.get("status") == "idle":
                # Forgejo-runner 13.2.0 self-reports the exact string v13.2.0.
                # The executed store path, rather than this field, pins its code.
                require(remote.get("labels") == ["mrjam-controller"] and remote.get("version") == "v13.2.0", "RUNNER_PROFILE_CHANGED")
                break
            require(time.monotonic() < deadline, "SYNTHETIC_RUNNER_START_TIMEOUT")
            time.sleep(0.25)
        checks["pinned_runner_authenticates_with_credential_reference"] = True
        status, _ = request("POST", registration.BASE + "/actions/workflows/synthetic.yml/dispatches", {"ref": "main"})
        require(status == 204, "SYNTHETIC_WORKFLOW_DISPATCH_FAILED")
        deadline = time.monotonic() + 90
        while True:
            require(runner.poll() is None, "SYNTHETIC_RUNNER_STOPPED")
            status, runs = request("GET", registration.BASE + "/actions/runs?limit=1")
            require(status == 200 and type(runs.get("workflow_runs")) is list, "SYNTHETIC_RUN_UNAVAILABLE")
            if runs["workflow_runs"] and runs["workflow_runs"][0].get("status") == "success":
                break
            if runs["workflow_runs"] and runs["workflow_runs"][0].get("status") in ("failure", "cancelled", "skipped"):
                runner_log.seek(0)
                diagnostic = runner_log.read(8192).decode("utf-8", errors="replace").replace(token, "SYNTHETIC_TOKEN_REDACTED").replace(saved[0][1], "SYNTHETIC_TOKEN_REDACTED")
                print(json.dumps({"synthetic_daemon_diagnostic": diagnostic}))
                raise RuntimeError("SYNTHETIC_RUN_FAILED")
            if time.monotonic() >= deadline:
                print(json.dumps({"synthetic_run_state": [{"status": item.get("status"), "conclusion": item.get("conclusion")} for item in runs["workflow_runs"]]}))
                raise RuntimeError("SYNTHETIC_RUN_TIMEOUT")
            time.sleep(0.25)
        checks["actual_repository_scoped_runner_executes_fixed_synthetic_job"] = True
        print(json.dumps({"decision": "passed", "scope": "entirely synthetic local Forgejo", "forgejo_version": "17.0.1",
                          "forgejo_store_path": str(Path(FORGEJO).parents[1]), "checks": checks,
                          "swagger_sha256": hashlib.sha256(Path(SWAGGER).read_bytes()).hexdigest(),
                          "controller_sha256": hashlib.sha256((ROOT / "reconcile.py").read_bytes()).hexdigest(),
                          "registrar_sha256": hashlib.sha256((ROOT / "register_runner.py").read_bytes()).hexdigest(),
                          "runner_store_path": str(Path(RUNNER).parents[1]),
                          "limitations": ["SQLite fixture only; production PostgreSQL and installed Forgejo build not observed", "No real user/repository/identity/secret accessed", "No SSO, production ACL or NixOS runner-service qualification", "The fixed synthetic job does not qualify the independent Rust/Elm worker chain", "API readback is not a distributed compare-and-swap"]}, sort_keys=True))
        return 0
    finally:
        for process in (runner, server):
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        if runner_log is not None:
            runner_log.close()
        shutil.rmtree(parent)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Only our own fixed refusal codes, never process output or credentials.
        code = str(error) if type(error) in (RuntimeError, reconcile.Refused, registration.api.Refused) and str(error).replace("_", "").isupper() else "QUALIFICATION_FAILED"
        print(json.dumps({"decision": "failed", "code": code}))
        raise SystemExit(1)
