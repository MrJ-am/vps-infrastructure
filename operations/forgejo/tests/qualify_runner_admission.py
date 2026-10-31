#!/usr/bin/env python3
"""Real specialized runner admission, disposable Forgejo/SQLite/loopback fixture.

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
import socket
import threading
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

FORGEJO = "/nix/store/qcrq6ngi273hak8l7ldv1k9zqq0cqg2h-forgejo-17.0.1/bin/forgejo"
RUNNER = "/nix/store/i1qhz0s051zyib9xc6kzmz5sgh299vbc-mrjam-forgejo-runner-13.2.0/bin/forgejo-runner"
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


class SyntheticCollector:
    """The fixed IPC endpoint returns invented metadata only, never an artifact."""
    def __init__(self, rules, group):
        self.calls = 0
        self.invalid = False
        self.stopped = threading.Event()
        self.policy_directory = Path("/etc/mrjam-forgejo-runner")
        self.socket_directory = Path("/run/mrjam-validation-collector")
        require(not self.policy_directory.exists() and not self.socket_directory.exists(), "SYNTHETIC_FIXED_PATH_COLLISION")
        self.policy_directory.mkdir(mode=0o755)
        policy = self.policy_directory / "admission.json"
        policy.write_text(json.dumps({"schema_version": 1, "rules_revision": rules}, sort_keys=True, separators=(",", ":")))
        policy.chmod(0o444)
        self.socket_directory.mkdir(mode=0o755)
        self.listener = socket.socket(socket.AF_UNIX)
        location = self.socket_directory / "request.sock"
        self.listener.bind(str(location)); location.chmod(0o660); os.chown(location, 0, group)
        self.listener.listen(2); self.listener.settimeout(0.2)
        self.receipt = json.dumps({"schema_version":1,"decision":"passed","proposal_sha256":"b"*64,"rules_revision":rules,
            "authority":"local-controller-receipt","collection":"retained-code-artifacts","authenticated_validation_authority":False,
            "artifacts":[{"name":name,"bytes":1,"sha256":"c"*64} for name in ["server","frontend.tar","verification.json"]]}, sort_keys=True,separators=(",",":")).encode()+b"\n"
        self.thread = threading.Thread(target=self.serve, daemon=True); self.thread.start()
    def serve(self):
        while not self.stopped.is_set():
            try: connection, _ = self.listener.accept()
            except TimeoutError: continue
            except OSError: return
            with connection:
                connection.settimeout(3)
                raw = b""
                try:
                    while len(raw) <= 65:
                        part = connection.recv(66-len(raw))
                        if not part: break
                        raw += part
                    self.calls += 1
                    if raw != b"b"*64+b"\n": self.invalid = True; continue
                    connection.sendall(self.receipt)
                except OSError: self.invalid = True
    def close(self):
        self.stopped.set(); self.listener.close(); self.thread.join(timeout=4)
        shutil.rmtree(self.socket_directory); shutil.rmtree(self.policy_directory)


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
    collector = None
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
        workflow = (ROOT / "independent-validation.yml").read_bytes()
        status, _ = request("POST", reconcile.path_for("mrjam-validation") + "/contents/.forgejo/workflows/independent-validation.yml", {
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
        runner_config["log"] = {"level": "error", "job_level": "error"}
        runner_config["server"]["connections"]["mrjam-validation"]["url"] = ORIGIN
        runner_config["host"]["workdir_parent"] = str(parent / "synthetic-jobs")
        runner_config["runner"]["envs"] = {}
        collector = SyntheticCollector(rules, user.pw_gid)
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
                require(remote.get("labels") == ["mrjam-controller"] and remote.get("version") == "v13.2.0+mrjam-bounded.1", "RUNNER_PROFILE_CHANGED")
                break
            require(time.monotonic() < deadline, "SYNTHETIC_RUNNER_START_TIMEOUT")
            time.sleep(0.25)
        checks["pinned_runner_authenticates_with_credential_reference"] = True
        def dispatch(ref, digest, expected):
            status, before = request("GET", registration.BASE + "/actions/runs?limit=1")
            require(status == 200, "SYNTHETIC_RUN_UNAVAILABLE")
            previous = before["workflow_runs"][0]["id"] if before["workflow_runs"] else 0
            status, _ = request("POST", registration.BASE + "/actions/workflows/independent-validation.yml/dispatches", {"ref": ref, "inputs": {"proposal_digest": digest}})
            require(status == 204, "SYNTHETIC_WORKFLOW_DISPATCH_FAILED")
            deadline = time.monotonic() + 90
            while True:
                require(runner.poll() is None, "SYNTHETIC_RUNNER_STOPPED")
                status, runs = request("GET", registration.BASE + "/actions/runs?limit=1")
                require(status == 200 and type(runs.get("workflow_runs")) is list, "SYNTHETIC_RUN_UNAVAILABLE")
                if runs["workflow_runs"] and runs["workflow_runs"][0]["id"] != previous:
                    state = runs["workflow_runs"][0].get("status")
                    if state in ("success", "failure", "cancelled", "skipped"):
                        if state != expected:
                            runner_log.seek(0)
                            codes = sorted(set(re.findall(r"MRJAM_[A-Z_]+", runner_log.read(65536).decode("utf-8", errors="replace"))))
                            print(json.dumps({"synthetic_fixed_refusal_codes": codes, "status": state}))
                        require(state == expected, "SYNTHETIC_UNEXPECTED_RUN_STATUS")
                        return
                require(time.monotonic() < deadline, "SYNTHETIC_RUN_TIMEOUT")
                time.sleep(0.25)
        dispatch("main", "b" * 64, "success")
        require(collector.calls == 1 and not collector.invalid, "SYNTHETIC_COLLECTION_MISMATCH")
        checks["exact_main_workflow_reaches_only_fixed_collector"] = True
        status, _ = request("POST", registration.BASE + "/branches", {"new_branch_name": "synthetic-equal", "old_branch_name": "main"})
        require(status == 201, "SYNTHETIC_BRANCH_CREATE_FAILED")
        dispatch("synthetic-equal", "b" * 64, "failure")
        require(collector.calls == 1, "UNAPPROVED_BRANCH_REACHED_COLLECTOR")
        checks["same_workflow_same_label_other_branch_refused"] = True
        dispatch("main", "$(touch /tmp/synthetic-input-must-not-run)", "failure")
        require(collector.calls == 1 and not Path("/tmp/synthetic-input-must-not-run").exists(), "INPUT_EXECUTED")
        checks["shell_input_is_data_and_refused_before_collector"] = True
        canary = parent / "synthetic-step-must-not-run"
        status, existing = request("GET", registration.BASE + "/contents/.forgejo/workflows/independent-validation.yml?ref=synthetic-equal")
        require(status == 200, "SYNTHETIC_WORKFLOW_READ_FAILED")
        changed = workflow.replace(b"exec mrjam-submit-validation", ("touch " + str(canary)).encode())
        status, _ = request("PUT", registration.BASE + "/contents/.forgejo/workflows/independent-validation.yml", {
            "branch": "synthetic-equal", "sha": existing["sha"], "message": "Synthetic forbidden step", "content": base64.b64encode(changed).decode("ascii")})
        require(status == 200, "SYNTHETIC_CHANGED_WORKFLOW_FAILED")
        dispatch("synthetic-equal", "b" * 64, "failure")
        require(collector.calls == 1 and not canary.exists(), "CANDIDATE_STEP_EXECUTED")
        checks["changed_candidate_step_never_executes"] = True
        print(json.dumps({"decision": "passed", "scope": "entirely synthetic local Forgejo", "forgejo_version": "17.0.1",
                          "forgejo_store_path": str(Path(FORGEJO).parents[1]), "checks": checks,
                          "swagger_sha256": hashlib.sha256(Path(SWAGGER).read_bytes()).hexdigest(),
                          "controller_sha256": hashlib.sha256((ROOT / "reconcile.py").read_bytes()).hexdigest(),
                          "registrar_sha256": hashlib.sha256((ROOT / "register_runner.py").read_bytes()).hexdigest(),
                          "runner_store_path": str(Path(RUNNER).parents[1]),
                          "limitations": ["SQLite fixture only; production PostgreSQL and installed Forgejo build not observed", "No real user/repository/identity/secret accessed", "No SSO, production ACL or NixOS runner-service qualification", "The root-owned collector is an invented receipt fixture, not the independent Rust/Elm validator", "API readback is not a distributed compare-and-swap"]}, sort_keys=True))
        return 0
    finally:
        if collector is not None:
            collector.close()
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
        require(len(sys.argv) == 2 and re.fullmatch(r"/nix/store/[a-z0-9]{32}-mrjam-forgejo-runner-13\.2\.0/bin/forgejo-runner", sys.argv[1]), "EXACT_SYNTHETIC_RUNNER_REQUIRED")
        RUNNER = sys.argv[1]
        raise SystemExit(main())
    except Exception as error:
        # Only our own fixed refusal codes, never process output or credentials.
        code = str(error) if type(error) in (RuntimeError, reconcile.Refused, registration.api.Refused) and str(error).replace("_", "").isupper() else "QUALIFICATION_FAILED"
        print(json.dumps({"decision": "failed", "code": code, "runner_store_path": str(Path(RUNNER).parents[1]), "production_access": False}))
        raise SystemExit(1)
