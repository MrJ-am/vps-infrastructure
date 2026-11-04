"""Closed Forgejo17 bootstrap/probe. Only the trusted local backend imports this.

No personal account fallback, password reset, general user listing, repository
content, caller-selected SQL, command or URL. Credentials never leave memory.
"""
import configparser
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time
import urllib.error
import urllib.request

FORGEJO = "@FORGEJO@/bin/forgejo"
PSQL = "@POSTGRES@/bin/psql"
FORGEJO_UID = 982
FORGEJO_GID = 982
INI = Path("/run/mrjam-forgejo/app.ini")
PID = Path("/run/mrjam-forgejo/forgejo.pid")
STATE = Path("/var/lib/mrjam-forgejo-bootstrap")
ACCOUNT = "mrjam-governance-bootstrap"
OWNER = "MrJ-am"
REPOSITORIES = ("Signature", "apprendre-a-demontrer", "etp-vie-affective", "matheval", "mrjam-plateforme", "mrjam-validation", "style-mrjam", "vision", "vps-infrastructure")
ORIGIN = "http://127.0.0.1:3004"
READ_SCOPES = "read:user,read:organization,read:repository"
WRITE_SCOPES = "read:user,write:organization,write:repository"
LABEL = re.compile(r"mrjam-governance-lease-[0-9a-f]{32}")
LIMIT = 131072

ACCOUNT_SQL = """BEGIN READ ONLY; SET LOCAL statement_timeout='3s';
SELECT json_build_object(
 'exists',EXISTS(SELECT FROM public.\"user\" WHERE lower_name='mrjam-governance-bootstrap'),
 'eligible',EXISTS(SELECT FROM public.\"user\" WHERE lower_name='mrjam-governance-bootstrap'
   AND name='mrjam-governance-bootstrap' AND type=0 AND login_type IN (0,1)
   AND login_source=0 AND coalesce(login_name,'')='' AND is_admin AND is_active
   AND NOT prohibit_login AND NOT must_change_password AND NOT is_restricted),
 'legacy_exists',EXISTS(SELECT FROM public.\"user\" WHERE lower_name='mrjam-admin'),
 'legacy_local_admin',EXISTS(SELECT FROM public.\"user\" WHERE lower_name='mrjam-admin'
   AND type=0 AND login_type IN (0,1) AND login_source=0 AND coalesce(login_name,'')=''
   AND is_admin AND is_active AND NOT prohibit_login))::text;
COMMIT;"""
COUNT_SQL = """BEGIN READ ONLY; SET LOCAL statement_timeout='3s';
SELECT count(*) FROM public.access_token WHERE uid=(SELECT id FROM public.\"user\" WHERE lower_name='mrjam-governance-bootstrap') AND name=:'lease';
COMMIT;"""
REVOKE_SQL = """BEGIN; SET LOCAL statement_timeout='3s'; SET LOCAL lock_timeout='2s';
DELETE FROM public.access_token WHERE uid=(SELECT id FROM public.\"user\" WHERE lower_name='mrjam-governance-bootstrap') AND name=:'lease';
COMMIT;"""


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def parse(data):
    require(type(data) is bytes and len(data) <= LIMIT, "RESPONSE_LIMIT")
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(Refused("JSON_NUMBER_REFUSED")))
    except Refused:
        raise
    except Exception:
        raise Refused("INVALID_JSON") from None


def private_file(path, maximum=65536, owner=0, mode=0o600):
    require(path.is_absolute() and all(part not in (".", "..") for part in path.parts), "PATH_REFUSED")
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:-1]:
            following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = following
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == owner
                and stat.S_IMODE(before.st_mode) == mode and 0 < before.st_size <= maximum, "FILE_REFUSED")
        data = source.read(maximum + 1)
        after = os.fstat(source.fileno())
        require(len(data) == before.st_size and (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), "FILE_CHANGED")
        return data


def publish(name, value):
    require(name in ("identity.json", "lease.json"), "STATE_NAME_REFUSED")
    target = STATE / name
    temporary = STATE / (name + ".pending")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        data = json.dumps(value, sort_keys=True).encode()
        require(os.write(fd, data) == len(data), "STATE_WRITE_FAILED")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, target)
    sync_state()


def sync_state():
    fd = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def forget_lease():
    (STATE / "lease.json").unlink()
    sync_state()


@contextmanager
def locked():
    require(os.geteuid() == 0, "ROOT_BACKEND_REQUIRED")
    os.umask(0o077)
    if not STATE.exists():
        STATE.mkdir(mode=0o700)
    info = STATE.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0 and stat.S_IMODE(info.st_mode) == 0o700, "STATE_DIRECTORY_REFUSED")
    fd = os.open(STATE / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600, "STATE_LOCK_REFUSED")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def command(arguments, data=b""):
    # The only callers below build fixed CLI or literal SQL operations.
    require(arguments[0] in (FORGEJO, PSQL) and len(data) <= 16384, "COMMAND_REFUSED")
    environment = {"HOME": "/var/lib/forgejo", "USER": "forgejo", "LANG": "C", "TZ": "UTC", "GOMAXPROCS": "2",
                   "FORGEJO_WORK_DIR": "/var/lib/forgejo", "FORGEJO_CUSTOM": "/var/lib/forgejo/custom"}
    process = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=environment, cwd="/var/lib/forgejo", user=FORGEJO_UID, group=FORGEJO_GID, extra_groups=[], start_new_session=True)
    try:
        process.stdin.write(data)
        process.stdin.close()
        selector = selectors.DefaultSelector()
        for stream in (process.stdout, process.stderr):
            selector.register(stream, selectors.EVENT_READ)
        out = {process.stdout: bytearray(), process.stderr: bytearray()}
        deadline = time.monotonic() + 25
        while selector.get_map():
            require(time.monotonic() < deadline, "COMMAND_DEADLINE")
            for key, _ in selector.select(0.25):
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                else:
                    out[key.fileobj].extend(chunk)
                    require(len(out[key.fileobj]) <= 8192, "COMMAND_OUTPUT_LIMIT")
        require(process.wait(timeout=1) == 0, "LOCAL_OPERATION_FAILED")
        return bytes(out[process.stdout])
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        for stream in (process.stdout, process.stderr):
            stream.close()


def sql(operation, label=None):
    require(operation in ("account", "count", "revoke"), "SQL_OPERATION_REFUSED")
    arguments = [PSQL, "-X", "-w", "-qAt", "-h", "/run/postgresql", "-d", "forgejo", "-v", "ON_ERROR_STOP=1"]
    if operation == "account":
        require(label is None, "SQL_OPERATION_REFUSED")
        result = parse(command(arguments, ACCOUNT_SQL.encode()))
        require(type(result) is dict and set(result) == {"exists", "eligible", "legacy_exists", "legacy_local_admin"}
                and all(type(x) is bool for x in result.values()), "ACCOUNT_SHAPE_REFUSED")
        return result
    require(type(label) is str and LABEL.fullmatch(label), "LEASE_NAME_REFUSED")
    arguments += ["-v", "lease=" + label]
    output = command(arguments, (COUNT_SQL if operation == "count" else REVOKE_SQL).encode())
    if operation == "count":
        require(output in (b"0\n", b"1\n"), "LEASE_COLLISION")
        return int(output)
    require(output == b"", "REVOKE_OUTPUT_REFUSED")


def validate_configuration():
    data = private_file(INI, owner=FORGEJO_UID, mode=0o400)
    # Forgejo permits unsectioned APP_NAME/RUN_MODE. Keep those separate from
    # service/database options; they must never act as inherited defaults.
    settings = configparser.ConfigParser(interpolation=None, strict=True, default_section="__forbidden_default__")
    try:
        settings.read_string("[__forgejo_root__]\n" + data.decode("utf-8"))
        required = {("service", "ENABLE_INTERNAL_SIGNIN"): "false", ("service", "ENABLE_BASIC_AUTHENTICATION"): "false",
                    ("service", "ENABLE_NOTIFY_MAIL"): "false", ("database", "DB_TYPE"): "postgres",
                    ("database", "HOST"): "/run/postgresql", ("database", "NAME"): "forgejo",
                    ("database", "USER"): "forgejo", ("database", "AUTO_MIGRATION"): "false",
                    ("server", "HTTP_ADDR"): "127.0.0.1", ("server", "HTTP_PORT"): "3004"}
        require(not settings.defaults(), "UNQUALIFIED_FORGEJO_PROFILE")
        require(all(settings.get(section, key).strip().lower() == value for (section, key), value in required.items()), "UNQUALIFIED_FORGEJO_PROFILE")
    except Refused:
        raise
    except Exception:
        raise Refused("CONFIGURATION_REFUSED") from None


def validate_running():
    # REQUIRE_SIGNIN_VIEW also protects /api/v1/version. Before a technical
    # credential exists, attest the selected immutable running ELF instead.
    try:
        pid = private_file(PID, maximum=32, owner=FORGEJO_UID, mode=0o600)
        require(re.fullmatch(rb"[1-9][0-9]{0,9}\n?", pid), "RUNNING_PROCESS_REFUSED")
        process = Path("/proc", pid.decode().strip())
        require(process.stat().st_uid == FORGEJO_UID and os.readlink(process / "exe") == str(Path(FORGEJO).with_name(".forgejo-wrapped")),
                "RUNNING_ARTIFACT_REFUSED")
    except OSError:
        raise Refused("RUNNING_PROCESS_INACCESSIBLE") from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *arguments):
        raise Refused("REDIRECT_REFUSED")


class API:
    def __init__(self, token):
        require(token is None or re.fullmatch(r"[0-9a-f]{40}", token), "TOKEN_FORMAT_REFUSED")
        self.token = token
        self.requests = 0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def get(self, path):
        require(path in ("/api/v1/version", "/api/v1/user", "/api/v1/orgs/MrJ-am")
                or path in tuple("/api/v1/repos/MrJ-am/" + name for name in REPOSITORIES), "API_ENDPOINT_REFUSED")
        self.requests += 1
        require(self.requests <= 16, "REQUEST_LIMIT")
        headers = {"Host": "forge.mrj.am", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "token " + self.token
        request = urllib.request.Request(ORIGIN + path, method="GET", headers=headers)
        try:
            with self.opener.open(request, timeout=4) as response:
                require(response.status == 200 and response.headers.get_content_type() == "application/json", "API_RESPONSE_REFUSED")
                require(response.headers.get("Content-Encoding") in (None, "identity"), "CONTENT_ENCODING_REFUSED")
                length = response.headers.get("Content-Length")
                require(length is None or (length.isdecimal() and len(length) <= 7 and int(length) <= LIMIT), "RESPONSE_LIMIT")
                return 200, parse(response.read(LIMIT + 1))
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            require(status in (401, 403, 404), "API_STATUS_REFUSED")
            return status, None
        except Refused:
            raise
        except Exception:
            raise Refused("API_UNAVAILABLE") from None


def cleanup():
    target = STATE / "lease.json"
    if not target.exists():
        require(not target.is_symlink(), "LEASE_JOURNAL_REFUSED")
        return False
    value = parse(private_file(target, maximum=512))
    require(type(value) is dict and set(value) == {"account", "label"} and value["account"] == ACCOUNT
            and type(value["label"]) is str and LABEL.fullmatch(value["label"]), "LEASE_JOURNAL_REFUSED")
    if sql("count", value["label"]) == 1:
        sql("revoke", value["label"])
    require(sql("count", value["label"]) == 0, "TOKEN_REVOCATION_FAILED")
    forget_lease()
    return True


def identity_attested():
    target = STATE / "identity.json"
    if not target.exists():
        require(not target.is_symlink(), "IDENTITY_JOURNAL_REFUSED")
        return False
    value = parse(private_file(target, maximum=512))
    require(value in ({"account": ACCOUNT, "phase": "creating"}, {"account": ACCOUNT, "phase": "created"}), "IDENTITY_JOURNAL_REFUSED")
    return value["phase"] == "created"


@contextmanager
def _lease(scopes):
    require(scopes in (READ_SCOPES, WRITE_SCOPES), "TOKEN_SCOPE_REFUSED")
    validate_configuration()
    validate_running()
    cleanup()
    require(identity_attested() and sql("account")["eligible"], "TECHNICAL_ACCOUNT_NOT_READY")
    label = "mrjam-governance-lease-" + os.urandom(16).hex()
    require(sql("count", label) == 0, "LEASE_COLLISION")
    publish("lease.json", {"account": ACCOUNT, "label": label})
    token = None
    try:
        output = command([FORGEJO, "--config", str(INI), "admin", "user", "generate-access-token",
                          "--username", ACCOUNT, "--token-name", label, "--scopes", scopes, "--raw"])
        require(re.fullmatch(rb"[0-9a-f]{40}\n", output), "TOKEN_FORMAT_REFUSED")
        token = output[:-1].decode("ascii")
        require(sql("count", label) == 1, "TOKEN_ISSUE_NOT_CONFIRMED")
        status, value = API(token).get("/api/v1/version")
        require(status == 200 and value == {"version": "17.0.1"}, "UNQUALIFIED_FORGEJO_VERSION")
        yield token
    finally:
        cleanup()
        if token is not None:
            require(API(token).get("/api/v1/user")[0] == 401, "REVOKED_TOKEN_STILL_AUTHENTICATES")


@contextmanager
def governance_lease():
    """Only a reviewed in-process backend may use this scoped temporary token.

    Its existing reconcile transport must continue to enforce the fixed nine
    repositories and reviewed observation-bound plans. Never return this token
    through an agent tool, environment, argv, file, or diagnostic.
    """
    with locked():
        with _lease(WRITE_SCOPES) as token:
            yield token


def bootstrap():
    validate_configuration()
    validate_running()
    cleanup()
    current = sql("account")
    if current["exists"]:
        require(identity_attested() and current["eligible"], "TECHNICAL_ACCOUNT_COLLISION")
        return {"decision": "unchanged", "technical_account_ready": True}
    require(not (STATE / "identity.json").exists(), "IDENTITY_STATE_CONFLICT")
    publish("identity.json", {"account": ACCOUNT, "phase": "creating"})
    # Generated password is captured and discarded inside command(), never an
    # argument or a retained credential. Internal Web/Basic login is disabled.
    command([FORGEJO, "--config", str(INI), "admin", "user", "create", "--username", ACCOUNT,
             "--email", "governance-bootstrap@mrj.am", "--admin", "--random-password", "--random-password-length", "64",
             "--must-change-password=false"])
    require(sql("account")["eligible"], "CREATED_ACCOUNT_NOT_ELIGIBLE")
    publish("identity.json", {"account": ACCOUNT, "phase": "created"})
    return {"decision": "created", "technical_account_ready": True}


def probe():
    validate_configuration()
    validate_running()
    recovered = cleanup()
    account = sql("account")
    result = {"schema_version": 1, "authority": "unverified_observation", "forgejo_version": "17.0.1",
              "technical_account_exists": account["exists"], "technical_account_eligible": account["eligible"],
              "technical_account_attested": identity_attested(), "legacy_admin_exists": account["legacy_exists"],
              "legacy_admin_local": account["legacy_local_admin"], "recovered_lease_revoked": recovered,
              "temporary_token_revoked": None, "api_admin": None, "organization_exists": None,
              "repositories": {name: {"exists": None, "admin": None, "empty": None, "main_default": None} for name in REPOSITORIES}}
    if not account["eligible"] or not result["technical_account_attested"]:
        return result
    with _lease(READ_SCOPES) as token:
        api = API(token)
        status, me = api.get("/api/v1/user")
        require(status == 200 and type(me) is dict and me.get("login") == ACCOUNT and type(me.get("is_admin")) is bool, "SELF_IDENTITY_REFUSED")
        result["api_admin"] = me["is_admin"]
        require(me["is_admin"], "TECHNICAL_ACCOUNT_NOT_ADMIN")
        status, org = api.get("/api/v1/orgs/MrJ-am")
        require(status in (200, 404), "ORGANIZATION_ACCESS_UNKNOWN")
        if status == 200:
            require(type(org) is dict and org.get("username") == OWNER, "ORGANIZATION_IDENTITY_REFUSED")
        result["organization_exists"] = status == 200
        for name in REPOSITORIES:
            status, repo = api.get("/api/v1/repos/MrJ-am/" + name)
            require(status in (200, 404), "REPOSITORY_ACCESS_UNKNOWN")
            if status == 404:
                result["repositories"][name] = {"exists": False, "admin": None, "empty": None, "main_default": None}
            else:
                require(type(repo) is dict and repo.get("name") == name and repo.get("full_name") == OWNER + "/" + name
                        and type(repo.get("permissions")) is dict and type(repo["permissions"].get("admin")) is bool
                        and type(repo.get("empty")) is bool and type(repo.get("default_branch")) is str, "REPOSITORY_SHAPE_REFUSED")
                result["repositories"][name] = {"exists": True, "admin": repo["permissions"]["admin"], "empty": repo["empty"], "main_default": repo["default_branch"] == "main"}
    result["temporary_token_revoked"] = True
    return result


def main(operation, arguments):
    if arguments or operation not in ("probe", "bootstrap", "cleanup"):
        return 64
    def interrupted(_signum, _frame):
        raise Refused("INTERRUPTED")
    old_signals = {number: signal.signal(number, interrupted) for number in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM)}
    signal.alarm(180)
    try:
        with locked():
            value = probe() if operation == "probe" else bootstrap() if operation == "bootstrap" else {"revoked": cleanup()}
        print(json.dumps(value, sort_keys=True))
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, Refused) and re.fullmatch(r"[A-Z_]+", str(error)) else {
            PermissionError: "LOCAL_PERMISSION_REFUSED", FileNotFoundError: "LOCAL_PATH_MISSING",
            subprocess.SubprocessError: "LOCAL_SUBPROCESS_REFUSED", BrokenPipeError: "LOCAL_PIPE_REFUSED"}.get(type(error), "LOCAL_BACKEND_FAILED")
        print(json.dumps({"decision": "refused", "code": code}, sort_keys=True))
        return 2
    finally:
        signal.alarm(0)
        for number, previous in old_signals.items():
            signal.signal(number, previous)
