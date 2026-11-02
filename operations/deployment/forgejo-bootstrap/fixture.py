"""Invented guest only. Broad fixture setup is not an installed backend entry."""
import base64
import importlib.util
import http.cookiejar
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

PACKAGE = Path(os.environ["SYNTHETIC_BOOTSTRAP_PACKAGE"])
FORGEJO = Path(os.environ["SYNTHETIC_FORGEJO_PACKAGE"])
ROOT = Path("/var/lib/synthetic-forgejo-proof")
spec = importlib.util.spec_from_file_location("core", PACKAGE / "libexec/core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
spec = importlib.util.spec_from_file_location("reconcile", "/etc/synthetic-forgejo-policy/reconcile.py")
reconcile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconcile)


def require(value, code):
    if not value: raise RuntimeError(code)


def command(arguments, data=None):
    result = subprocess.run(arguments, input=data, capture_output=True, timeout=90)
    if result.returncode and arguments[-1:] == ["migrate"]:
        # This one bootstrap command contains no generated credential. Its
        # invented-schema diagnostics are retained only inside the test guest.
        (ROOT / "migration-error").write_bytes((result.stderr + result.stdout)[-8192:])
    require(result.returncode == 0, "FIXTURE_COMMAND_FAILED")
    return result.stdout


def sql(statement):
    return command(["runuser", "-u", "postgres", "--", "psql", "-X", "-w", "-qAt", "-h", "/run/postgresql", "-d", "forgejo", "-v", "ON_ERROR_STOP=1"], statement.encode()).decode().strip()


def cli(*arguments):
    return command(["runuser", "-u", "forgejo", "--", "env", "USER=forgejo", "HOME=/var/lib/forgejo",
                    "FORGEJO_WORK_DIR=/var/lib/forgejo", "FORGEJO_CUSTOM=/var/lib/forgejo/custom", str(FORGEJO / "bin/forgejo"),
                    "--config", "/etc/synthetic-forgejo.ini", *arguments])


def prepare():
    ROOT.mkdir(mode=0o700)
    command(["install", "-d", "-m", "0750", "-o", "forgejo", "-g", "forgejo", "/var/lib/forgejo"])
    for directory in ("/var/lib/forgejo/custom/conf", "/var/lib/forgejo/repositories"):
        command(["install", "-d", "-m", "0700", "-o", "forgejo", "-g", "forgejo", directory])
    for name, value in (("secret_key", "SYNTHETIC-SECRET-KEY-NOT-PRODUCTION"), ("internal_token", "SYNTHETIC-INTERNAL-TOKEN-NOT-PRODUCTION"), ("oauth2_jwt_secret", "A" * 43)):
        path = Path("/var/lib/forgejo/custom/conf", name)
        path.write_text(value)
        path.chmod(0o400)
        os.chown(path, core.FORGEJO_UID, core.FORGEJO_GID)
    cli("migrate")
    for name in ("MrJam", "mrjam-admin"):
        cli("admin", "user", "create", "--username", name, "--email", name.lower() + "@synthetic.invalid", "--admin",
            "--random-password", "--random-password-length", "64", "--must-change-password=false")
    # This is invented proof that an old name could now identify an SSO user.
    sql("UPDATE public.\"user\" SET login_type=6,login_source=999,login_name='SYNTHETIC-OWNER' WHERE lower_name='mrjam-admin'")
    sql(Path("/etc/forgejo-adopt-runtime-role.sql").read_text())
    (ROOT / "personal-before").write_text(personal())


def personal():
    return sql("SELECT coalesce(json_agg(json_build_array(name,login_type,login_source,login_name,passwd,salt,is_admin))::text,'[]') FROM (SELECT * FROM public.\"user\" WHERE lower_name IN ('mrjam','mrjam-admin') ORDER BY lower_name) x")


def run(name):
    result = subprocess.run([str(PACKAGE / "bin" / ("mrjam-forgejo-" + name))], capture_output=True, timeout=90)
    value = json.loads(result.stdout)
    if result.returncode:
        code = value.get("code")
        require(type(code) is str and re.fullmatch(r"[A-Z_]+", code), "HELPER_ERROR_SHAPE")
        raise RuntimeError("HELPER_" + code)
    require(value.get("decision") != "refused", "HELPER_REFUSED")
    return value


def absent():
    value = run("probe")
    require(value["technical_account_exists"] is False and value["legacy_admin_exists"] is True and value["legacy_admin_local"] is False, "ABSENT_OR_SSO_ACCOUNT_ASSUMED")
    require(value["organization_exists"] is None and value["temporary_token_revoked"] is None, "ABSENCE_INVENTED_STATE")
    require(sql("SELECT count(*) FROM access_token") == "0", "ABSENT_PROBE_ISSUED_TOKEN")
    require(personal() == (ROOT / "personal-before").read_text(), "PERSONAL_ACCOUNT_CHANGED")


def verify_bootstrap():
    require(core.sql("account")["eligible"] and core.identity_attested(), "BOOTSTRAP_NOT_ELIGIBLE")
    require(run("bootstrap")["decision"] == "unchanged", "BOOTSTRAP_NOT_IDEMPOTENT")
    value = run("probe")
    require(value["api_admin"] is True and value["organization_exists"] is False and value["temporary_token_revoked"] is True, "NEW_ADMIN_PROBE_WRONG")
    require(all(row["exists"] is False for row in value["repositories"].values()), "PROBE_CREATED_REPOSITORY")
    require(sql("SELECT count(*) FROM access_token") == "0", "PROBE_TOKEN_RETAINED")
    require(personal() == (ROOT / "personal-before").read_text(), "PERSONAL_ACCOUNT_CHANGED")


def password_routes_disabled():
    # An invented known-valid local password is held only in this process. It
    # verifies the global profile also prevents a valid technical Web/Basic login.
    username = "synthetic-disabled-login"
    output = cli("admin", "user", "create", "--username", username, "--email", "disabled@synthetic.invalid",
                 "--random-password", "--random-password-length", "64", "--must-change-password=false")
    match = re.search(rb"generated random password is '([^\n]{64})'\n", output)
    require(match is not None, "FIXTURE_RANDOM_PASSWORD_SHAPE")
    password = match.group(1).decode()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), core.NoRedirect())
    auth = base64.b64encode((username + ":" + password).encode()).decode()
    request = urllib.request.Request(core.ORIGIN + "/api/v1/user", headers={"Authorization": "Basic " + auth, "Host": "forge.mrj.am"})
    try:
        with opener.open(request, timeout=8):
            raise RuntimeError("VALID_BASIC_PASSWORD_ACCEPTED")
    except urllib.error.HTTPError as error:
        require(error.code == 401, "BASIC_REFUSAL_STATUS")
        error.close()
    with opener.open(urllib.request.Request(core.ORIGIN + "/user/login", headers={"Host": "forge.mrj.am"}), timeout=8) as response:
        require(response.status == 200, "WEB_LOGIN_PAGE_STATUS")
        body = response.read(262145)
        require(len(body) <= 262144, "WEB_LOGIN_PAGE_SIZE")
    # Forgejo17 uses Go CrossOriginProtection, not a hidden CSRF form token.
    # Supply the same-origin request shape so the disabled internal login is
    # exercised rather than failing an unrelated cross-origin guard.
    payload = urllib.parse.urlencode({"user_name": username, "password": password}).encode()
    request = urllib.request.Request(core.ORIGIN + "/user/login", payload,
                                    {"Host": "forge.mrj.am", "Origin": "https://forge.mrj.am", "Sec-Fetch-Site": "same-origin", "Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with opener.open(request, timeout=8):
            raise RuntimeError("VALID_WEB_PASSWORD_ACCEPTED")
    except urllib.error.HTTPError as error:
        require(error.code == 403, "WEB_REFUSAL_STATUS")
        error.close()


def api(token, method, path, value=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), core.NoRedirect())
    data = None if value is None else json.dumps(value).encode()
    request = urllib.request.Request(core.ORIGIN + path, data, {"Authorization": "token " + token, "Content-Type": "application/json", "Host": "forge.mrj.am"}, method=method)
    try:
        with opener.open(request, timeout=8) as response:
            body = response.read(core.LIMIT)
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        return status, None


def seed_and_protect():
    with core.governance_lease() as token:
        require(api(token, "POST", "/api/v1/orgs", {"username": "MrJ-am", "visibility": "private"})[0] == 201, "FIXTURE_ORG_CREATE_FAILED")
        require(api(token, "POST", "/api/v1/orgs/MrJ-am/repos", {"name": "synthetic-unrelated", "private": True, "auto_init": True, "default_branch": "main"})[0] == 201, "FIXTURE_SENTINEL_CREATE_FAILED")
        policy = {"schema_version": 2, "owner": "MrJ-am", "forgejo_version": "17.0.1", "rules_revision": "1" * 40,
                  "controller_revision": "2" * 40, "phase": "bootstrap-repositories", "repositories": sorted(core.REPOSITORIES)}
        transport = reconcile.Transport(token)
        plan = reconcile.plan(policy, reconcile.observe(transport, policy))
        result = reconcile.apply(transport, policy, plan, consume=lambda _: None)
        require(result["operations_applied"] == 9, "EXISTING_CONTROLLER_BOOTSTRAP_FAILED")
        for name in core.REPOSITORIES:
            require(api(token, "POST", "/api/v1/repos/MrJ-am/" + name + "/contents/README.txt", {
                "branch": "main", "message": "Invented public source", "content": base64.b64encode(b"invented public source only\n").decode()})[0] == 201, "FIXTURE_SOURCE_IMPORT_FAILED")
        policy["phase"] = "protect-main"
        transport = reconcile.Transport(token)
        plan = reconcile.plan(policy, reconcile.observe(transport, policy))
        require(reconcile.apply(transport, policy, plan, consume=lambda _: None)["operations_applied"] == 9, "SCOPED_TOKEN_CANNOT_PROTECT")
        require(api(token, "POST", "/api/v1/repos/MrJ-am/vision/contents/forbidden.txt", {
            "branch": "main", "message": "Must be refused", "content": base64.b64encode(b"forbidden\n").decode()})[0] in (403, 405), "ADMIN_BYPASSED_PROTECTION")
    require(sql("SELECT count(*) FROM access_token") == "0", "GOVERNANCE_TOKEN_RETAINED")


def populated():
    value = run("probe")
    require(value["organization_exists"] and value["api_admin"] and value["temporary_token_revoked"], "POPULATED_PROBE_FAILED")
    require(all(row == {"exists": True, "admin": True, "empty": False, "main_default": True} for row in value["repositories"].values()), "REPOSITORY_CAPABILITY_MISMATCH")
    require(sql("SELECT count(*) FROM repository") == "10", "UNRELATED_REPOSITORY_CHANGED")
    require(personal() == (ROOT / "personal-before").read_text(), "PERSONAL_ACCOUNT_CHANGED")
    require(sql("SELECT count(*) FROM access_token") == "0", "PROBE_TOKEN_RETAINED")
    (ROOT / "probe-result.json").write_text(json.dumps(value, sort_keys=True))


def interrupted_lease():
    # The exact issued token never leaves this guest process.
    with core.locked():
        label = "mrjam-governance-lease-" + "d" * 32
        require(core.sql("count", label) == 0, "FIXTURE_LEASE_COLLISION")
        core.publish("lease.json", {"account": core.ACCOUNT, "label": label})
        output = core.command([core.FORGEJO, "--config", str(core.INI), "admin", "user", "generate-access-token",
                               "--username", core.ACCOUNT, "--token-name", label, "--scopes", core.READ_SCOPES, "--raw"])
        require(re.fullmatch(rb"[0-9a-f]{40}\n", output), "FIXTURE_TOKEN_SHAPE")
        require(core.API(output.decode().strip()).get("/api/v1/user")[0] == 200, "FIXTURE_TOKEN_NOT_ACTIVE")
    # Deliberately leave only the nonsecret journal as if SIGKILL interrupted the
    # wrapper. The next fixed cleanup command must revoke exactly this lease.
    require(run("cleanup")["revoked"] is True and run("cleanup")["revoked"] is False, "CRASH_CLEANUP_NOT_IDEMPOTENT")
    require(core.API(output.decode().strip()).get("/api/v1/user")[0] == 401, "CRASH_TOKEN_STILL_ACTIVE")
    require(sql("SELECT count(*) FROM access_token") == "0", "CRASH_TOKEN_RETAINED")


def no_leak():
    data = command(["journalctl", "--no-pager", "-o", "cat", "-u", "mrjam-forgejo-bootstrap", "-u", "mrjam-forgejo-probe"])
    for marker in (b"generated random password", b"Access token was successfully", b"SYNTHETIC-OWNER", b"SYNTHETIC-SECRET", b"governance-bootstrap@mrj.am"):
        require(marker not in data, "PRIVATE_DIAGNOSTIC")
    require(personal() == (ROOT / "personal-before").read_text(), "PERSONAL_ACCOUNT_CHANGED")


ACTIONS = {"prepare": prepare, "absent": absent, "bootstrap": verify_bootstrap, "seed": seed_and_protect,
           "populated": populated, "interrupted": interrupted_lease, "no-leak": no_leak, "password-routes": password_routes_disabled}
if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in ACTIONS, "FIXTURE_SCOPE")
        ACTIONS[sys.argv[1]]()
    except Exception as error:
        code = str(error) if isinstance(error, RuntimeError) and re.fullmatch(r"[A-Z_]+", str(error)) else type(error).__name__
        print("SYNTHETIC_FORGEJO_FAILED:" + code, file=sys.stderr)
        raise SystemExit(1)
