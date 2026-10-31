#!/usr/bin/env python3
"""Closed Forgejo 17.0.1 metadata reconciliation, executed by a local controller.

The command line has only `plan` and `apply`; no URL, path, SQL or command is
accepted. The API token is a systemd credential and is never printed. This code
does not migrate repositories, inspect their content, register runners, or
change users/teams/secrets. Tests inject a loopback-only synthetic transport.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import struct
import sys
import time
import urllib.error
import urllib.request

OWNER = "MrJ-am"
VERSION = "17.0.1"
REPOSITORIES = frozenset(("mrjam-plateforme", "mrjam-validation", "vps-infrastructure", "vision", "matheval", "Signature", "style-mrjam", "apprendre-a-demontrer", "etp-vie-affective"))
POLICY_PATH = "/etc/mrjam-forgejo/policy.json"
PLAN_PATH = "/etc/mrjam-forgejo/reconcile-plan.json"
CREDENTIAL_PATH = "/run/credentials/mrjam-forgejo-policy.service/forgejo-token"
STATE_PATH = "/var/lib/mrjam-forgejo-policy"
ORIGIN = "http://127.0.0.1:3004"
MAX_BYTES = 131072
HEX = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
TIMEOUT = 5


class Refused(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(value, code="INVALID_INPUT"):
    if not value:
        raise Refused(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "DUPLICATE_KEY")
        result[key] = value
    return result


def parse(data):
    require(type(data) is bytes and len(data) <= MAX_BYTES, "INPUT_LIMIT")
    try:
        result = json.loads(data, object_pairs_hook=_pairs, parse_constant=lambda _: (_ for _ in ()).throw(Refused("INVALID_NUMBER")))
    except Refused:
        raise
    except Exception:
        raise Refused("INVALID_JSON") from None
    return result


def exact(value, names):
    require(type(value) is dict and set(value) == set(names), "INVALID_FIELDS")


def credential_acl(uid, permission):
    # Linux POSIX ACL xattr v2. Group mode bits can be the ACL mask rather than
    # permissions granted to the owning group (systemd LoadCredential behavior).
    return struct.pack("<I", 2) + b"".join(struct.pack("<HHI", tag, bits, identifier) for tag, bits, identifier in (
        (1, permission, 0xffffffff), (2, permission, uid), (4, 0, 0xffffffff),
        (16, permission, 0xffffffff), (32, 0, 0xffffffff)))


def systemd_credential_permissions(path, descriptor, info):
    # No generic permission relaxation: exactly the observed systemd ACL for
    # this service user, a root-only group, and a read-only credential mount.
    path = str(path)
    require(path in (CREDENTIAL_PATH, "/run/credentials/mrjam-forgejo-registration.service/forgejo-token"), "UNSAFE_CREDENTIAL")
    require(os.getuid() != 0 and info.st_uid == 0 and info.st_gid == 0
            and stat.S_IMODE(info.st_mode) == 0o440, "UNSAFE_CREDENTIAL")
    require(os.getxattr(descriptor, "system.posix_acl_access") == credential_acl(os.getuid(), 4)
            and os.fstatvfs(descriptor).f_flag & os.ST_RDONLY, "UNSAFE_CREDENTIAL")
    for ancestor in ("/", "/run", "/run/credentials"):
        entry = os.lstat(ancestor)
        require(stat.S_ISDIR(entry.st_mode) and entry.st_uid == 0 and entry.st_gid == 0
                and stat.S_IMODE(entry.st_mode) == 0o755, "UNSAFE_CREDENTIAL")
    parent = os.open(str(Path(path).parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        entry = os.fstat(parent)
        require(entry.st_uid == 0 and entry.st_gid == 0 and stat.S_IMODE(entry.st_mode) == 0o550
                and os.getxattr(parent, "system.posix_acl_access") == credential_acl(os.getuid(), 5)
                and os.fstatvfs(parent).f_flag & os.ST_RDONLY, "UNSAFE_CREDENTIAL")
        opened = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            current = os.fstat(opened)
            require((current.st_dev, current.st_ino) == (info.st_dev, info.st_ino), "UNSAFE_CREDENTIAL")
        finally:
            os.close(opened)
    finally:
        os.close(parent)


def document(path, *, credential=False):
    """Only callers holding fixed paths use this reader; no symlink/FIFO/echo."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "UNSAFE_FILE")
            require(before.st_uid in (0, os.getuid()) and not before.st_mode & 0o022, "UNSAFE_FILE")
            if credential:
                if before.st_mode & 0o077:
                    systemd_credential_permissions(path, stream.fileno(), before)
            limit = 512 if credential else MAX_BYTES
            require(0 < before.st_size <= limit, "INPUT_LIMIT")
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            require(len(data) == before.st_size and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), "INPUT_CHANGED")
            if credential:
                token = data.decode("ascii").removesuffix("\n")
                require(re.fullmatch(r"[A-Za-z0-9_-]{20,256}", token) is not None, "INVALID_CREDENTIAL")
                return token
            return parse(data)
    except Refused:
        raise
    except Exception:
        raise Refused("INPUT_UNAVAILABLE") from None


def validate_policy(value):
    exact(value, ("schema_version", "owner", "forgejo_version", "rules_revision", "controller_revision", "phase", "repositories"))
    require(type(value["schema_version"]) is int and value["schema_version"] == 2)
    require(value["owner"] == OWNER and value["forgejo_version"] == VERSION, "UNSUPPORTED_TARGET")
    require(value["phase"] in ("bootstrap-repositories", "protect-main", "operate-validation"), "UNMANAGED_PHASE")
    for key in ("rules_revision", "controller_revision"):
        require(type(value[key]) is str and COMMIT.fullmatch(value[key]) is not None, "INVALID_REVISION")
    repositories = value["repositories"]
    require(type(repositories) is list and repositories and all(type(name) is str and name in REPOSITORIES for name in repositories), "UNMANAGED_REPOSITORY")
    require(repositories == sorted(set(repositories)), "DUPLICATE_REPOSITORY")
    require(value["phase"] != "operate-validation" or "mrjam-validation" in repositories, "VALIDATION_REPOSITORY_REQUIRED")
    return value


def desired_protection():
    # All supported properties are explicit; pre-existing bypass lists are
    # removed only as part of the reviewed main-rule operation.
    return {
        "branch_name": "main",
        "rule_name": "main",
        "enable_push": False,
        "enable_push_whitelist": False,
        "push_whitelist_usernames": [],
        "push_whitelist_teams": [],
        "push_whitelist_deploy_keys": False,
        "enable_merge_whitelist": False,
        "merge_whitelist_usernames": [],
        "merge_whitelist_teams": [],
        "enable_status_check": True,
        "status_check_contexts": ["mrjam/independent-validation"],
        "required_approvals": 1,
        "enable_approvals_whitelist": False,
        "approvals_whitelist_username": [],
        "approvals_whitelist_teams": [],
        "block_on_rejected_reviews": True,
        "block_on_official_review_requests": True,
        "block_on_outdated_branch": True,
        "dismiss_stale_approvals": True,
        "ignore_stale_approvals": False,
        "require_signed_commits": False,
        "protected_file_patterns": "",
        "unprotected_file_patterns": "",
        "apply_to_admins": True,
    }


def path_for(name):
    require(name in REPOSITORIES, "UNMANAGED_REPOSITORY")
    return "/api/v1/repos/" + OWNER + "/" + name


def allowed_request(method, path):
    if method == "GET" and path == "/api/v1/version":
        return True
    if method == "POST" and path == "/api/v1/orgs/" + OWNER + "/repos":
        return True
    if method == "GET" and path == path_for("mrjam-validation") + "/branches/main":
        return True
    for name in REPOSITORIES:
        base = path_for(name)
        if (method in ("GET", "PATCH") and path == base) or (method == "POST" and path == base + "/branch_protections") or (method in ("GET", "PATCH") and path == base + "/branch_protections/main"):
            return True
    return False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Refused("REDIRECT_REFUSED")


class Transport:
    def __init__(self, token, *, synthetic_port=None):
        require(type(token) is str and re.fullmatch(r"[A-Za-z0-9_-]{20,256}", token) is not None, "INVALID_CREDENTIAL")
        require(synthetic_port is None or type(synthetic_port) is int and 1024 <= synthetic_port <= 65535, "INVALID_SYNTHETIC_PORT")
        self.origin = ORIGIN if synthetic_port is None else "http://127.0.0.1:" + str(synthetic_port)
        self.token = token
        # Only host-local API traffic; systemd additionally denies non-loopback.
        # Do not delegate a token to an inherited HTTP proxy.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.requests = 0

    def endpoint_allowed(self, method, path):
        return allowed_request(method, path)

    def request(self, method, path, body=None, *, missing=False):
        require(self.endpoint_allowed(method, path), "UNMANAGED_ENDPOINT")
        self.requests += 1
        require(self.requests <= 160, "REQUEST_LIMIT")
        data = None if body is None else canonical(body)
        require(data is None or len(data) <= MAX_BYTES, "INPUT_LIMIT")
        request = urllib.request.Request(self.origin + path, data=data, method=method,
                                         headers={"Authorization": "token " + self.token, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self.opener.open(request, timeout=TIMEOUT) as response:
                require(response.status in (200, 201), "UNEXPECTED_STATUS")
                require(response.headers.get_content_type() == "application/json", "UNEXPECTED_CONTENT_TYPE")
                encoding = response.headers.get("Content-Encoding")
                require(encoding is None or encoding == "identity", "CONTENT_ENCODING_REFUSED")
                length = response.headers.get("Content-Length")
                require(length is None or re.fullmatch(r"[0-9]{1,7}", length) and int(length) <= MAX_BYTES, "RESPONSE_LIMIT")
                return parse(response.read(MAX_BYTES + 1))
        except urllib.error.HTTPError as error:
            if error.code == 404 and missing and method == "GET":
                error.close()
                return None
            error.close()
            raise Refused("API_REJECTED") from None
        except Refused:
            raise
        except Exception:
            raise Refused("TRANSPORT_FAILED") from None


def filter_protection(raw):
    require(type(raw) is dict, "INVALID_PROTECTION")
    expected = desired_protection()
    result = {}
    for field, prototype in expected.items():
        require(field in raw, "API_FIELD_MISSING")
        value = raw[field]
        # Forgejo serializes empty optional lists as null in some profiles.
        if type(prototype) is list and value is None:
            value = []
        require(type(value) is type(prototype), "API_FIELD_TYPE")
        if type(value) is list:
            # Existing identities, teams and extra checks require a separate
            # adoption policy. Never return their names to the calling agent.
            if field == "status_check_contexts":
                require(value in ([], ["mrjam/independent-validation"]), "EXISTING_POLICY_REQUIRES_ADOPTION")
            else:
                require(value == [], "EXISTING_POLICY_REQUIRES_ADOPTION")
        elif type(value) is str:
            require(value == prototype, "EXISTING_POLICY_REQUIRES_ADOPTION")
        elif type(value) is int:
            require(0 <= value <= 100, "API_FIELD_VALUE")
        result[field] = value
    require(result["branch_name"] == "main", "WRONG_BRANCH")
    require(result["required_approvals"] <= 1 and result["require_signed_commits"] is False, "STRONGER_EXISTING_POLICY")
    require(result["enable_merge_whitelist"] is False and result["enable_approvals_whitelist"] is False, "STRONGER_EXISTING_POLICY")
    return result


def observe_repository(api, name):
    raw = api.request("GET", path_for(name), missing=True)
    if raw is None:
        return None
    require(type(raw) is dict and raw.get("name") == name and raw.get("full_name") == OWNER + "/" + name, "REPOSITORY_IDENTITY_CHANGED")
    require(type(raw.get("id")) is int and raw["id"] > 0, "REPOSITORY_IDENTITY_CHANGED")
    for field in ("private", "archived", "mirror", "empty", "has_actions"):
        require(type(raw.get(field)) is bool, "API_FIELD_TYPE")
    require(not raw["archived"] and not raw["mirror"], "REPOSITORY_ADOPTION_REFUSED")
    require(raw.get("default_branch") == "main", "DEFAULT_BRANCH_ADOPTION_REQUIRED")
    protection = api.request("GET", path_for(name) + "/branch_protections/main", missing=True)
    return {"id": raw["id"], "private": raw["private"], "default_branch": "main", "empty": raw["empty"], "actions_enabled": raw["has_actions"],
            "protection": None if protection is None else filter_protection(protection)}


def observe(api, policy):
    validate_policy(policy)
    version = api.request("GET", "/api/v1/version")
    require(type(version) is dict and version.get("version") == VERSION, "UNQUALIFIED_FORGEJO_VERSION")
    result = {"schema_version": 2, "authority": "unverified_observation", "forgejo_version": VERSION,
              "repositories": {name: observe_repository(api, name) for name in policy["repositories"]}}
    if policy["phase"] == "operate-validation":
        result["rules_head"] = observe_rules_head(api, policy)
    return result


def observe_rules_head(api, policy):
    branch = api.request("GET", path_for("mrjam-validation") + "/branches/main")
    require(type(branch) is dict and branch.get("name") == "main" and type(branch.get("commit")) is dict
            and branch["commit"].get("id") == policy["rules_revision"], "UNQUALIFIED_RULES_HEAD")
    return policy["rules_revision"]


def plan(policy, snapshot, *, now=None):
    validate_policy(policy)
    fields = ("schema_version", "authority", "forgejo_version", "repositories")
    exact(snapshot, fields + (("rules_head",) if policy["phase"] == "operate-validation" else ()))
    if policy["phase"] == "operate-validation":
        require(snapshot["rules_head"] == policy["rules_revision"], "UNQUALIFIED_RULES_HEAD")
    require(snapshot["schema_version"] == 2 and snapshot["forgejo_version"] == VERSION and snapshot["authority"] == "unverified_observation", "INVALID_OBSERVATION")
    require(type(snapshot["repositories"]) is dict and set(snapshot["repositories"]) == set(policy["repositories"]), "INVALID_OBSERVATION")
    actions = []
    for name in policy["repositories"]:
        current = snapshot["repositories"][name]
        if current is None:
            require(policy["phase"] == "bootstrap-repositories", "SOURCE_IMPORT_REQUIRED")
            actions.append({"repository": name, "operation": "create-private-repository", "before": None})
        else:
            wanted_actions = policy["phase"] == "operate-validation" and name == "mrjam-validation"
            if policy["phase"] == "operate-validation":
                require(current["empty"] is False and current["protection"] == desired_protection(), "UNQUALIFIED_PROTECTION")
            if current["actions_enabled"] and not wanted_actions:
                actions.append({"repository": name, "operation": "disable-candidate-actions", "before": current})
            if wanted_actions and not current["actions_enabled"]:
                actions.append({"repository": name, "operation": "enable-validation-actions", "before": current})
            if policy["phase"] == "protect-main":
                require(current["empty"] is False, "SOURCE_IMPORT_REQUIRED")
            if policy["phase"] == "protect-main" and current["protection"] != desired_protection():
                actions.append({"repository": name, "operation": "protect-main", "before": current})
    now = int(time.time()) if now is None else now
    return {"schema_version": 2, "policy_sha256": digest(policy), "observation_sha256": digest(snapshot),
            "created_unix": now, "expires_unix": now + 3600, "operations": actions,
            "scope": "repository-metadata-only", "existing_visibility": "preserved", "content_or_identity_changes": False}


def validate_plan(value, policy, snapshot, now):
    exact(value, ("schema_version", "policy_sha256", "observation_sha256", "created_unix", "expires_unix", "operations", "scope", "existing_visibility", "content_or_identity_changes"))
    require(type(value["created_unix"]) is int and type(value["expires_unix"]) is int and value["created_unix"] <= now <= value["expires_unix"] <= value["created_unix"] + 3600, "PLAN_EXPIRED")
    require(value == plan(policy, snapshot, now=value["created_unix"]), "STALE_OR_CHANGED_PLAN")


def apply(api, policy, approved_plan, *, consume, now=None):
    """The local controller provides a durable one-use consume function.

    Readback detects drift but Forgejo has no transaction/CAS spanning these
    APIs. The controller therefore needs exclusive administrative scheduling.
    Any failed/partial apply requires a fresh observation and new reviewed plan.
    """
    now = int(time.time()) if now is None else now
    snapshot = observe(api, policy)
    current_plan = plan(policy, snapshot, now=now)
    if not current_plan["operations"]:
        # Do not consume or mutate on a replay of an already converged policy.
        return {"decision": "no-changes", "operations_applied": 0, "policy_sha256": digest(policy), "observation_sha256": digest(snapshot)}
    validate_plan(approved_plan, policy, snapshot, now)
    consume(digest(approved_plan))
    count = 0
    states = snapshot["repositories"].copy()
    for operation in approved_plan["operations"]:
        name = operation["repository"]
        before = observe_repository(api, name)
        require(before == states[name], "STATE_CHANGED_BEFORE_WRITE")
        operation_name = operation["operation"]
        if operation_name == "create-private-repository":
            require(before is None, "STATE_CHANGED_BEFORE_WRITE")
            api.request("POST", "/api/v1/orgs/" + OWNER + "/repos", {
                "name": name, "private": True, "auto_init": False, "default_branch": "main", "trust_model": "committer"})
        elif operation_name == "disable-candidate-actions":
            api.request("PATCH", path_for(name), {"has_actions": False})
        elif operation_name == "enable-validation-actions":
            require(policy["phase"] == "operate-validation" and name == "mrjam-validation"
                    and before is not None and before["protection"] == desired_protection(), "UNMANAGED_OPERATION")
            observe_rules_head(api, policy)
            api.request("PATCH", path_for(name), {"has_actions": True})
        elif operation_name == "protect-main":
            require(before is not None, "REPOSITORY_MISSING")
            method, suffix = ("POST", "/branch_protections") if before["protection"] is None else ("PATCH", "/branch_protections/main")
            body = desired_protection()
            if method == "PATCH":
                body = {key: value for key, value in body.items() if key not in ("branch_name", "rule_name")}
            api.request(method, path_for(name) + suffix, body)
        else:
            raise Refused("UNMANAGED_OPERATION")
        count += 1
        after = observe_repository(api, name)
        require(after is not None, "READBACK_FAILED")
        if before is not None:
            require(after["id"] == before["id"] and after["private"] == before["private"], "REPOSITORY_IDENTITY_CHANGED")
        if operation_name == "create-private-repository":
            require(after["private"] is True, "READBACK_FAILED")
            if after["actions_enabled"]:
                # Newly created repositories inherit server unit defaults;
                # always close Actions before accepting the new repository.
                api.request("PATCH", path_for(name), {"has_actions": False})
                after = observe_repository(api, name)
                require(after is not None and after["private"] is True and after["actions_enabled"] is False, "READBACK_FAILED")
        elif operation_name == "disable-candidate-actions":
            require(after["actions_enabled"] is False and after["protection"] == before["protection"], "READBACK_FAILED")
        elif operation_name == "enable-validation-actions":
            require(after["actions_enabled"] is True and after["protection"] == before["protection"], "READBACK_FAILED")
        elif operation_name == "protect-main":
            require(after["protection"] == desired_protection() and after["actions_enabled"] is False, "READBACK_FAILED")
        states[name] = after
    final = observe(api, policy)
    require(not plan(policy, final, now=now)["operations"], "CONVERGENCE_FAILED")
    return {"decision": "applied", "operations_applied": count, "policy_sha256": digest(policy), "plan_sha256": digest(approved_plan), "observation_sha256": digest(final)}


def _expired(signum, frame):
    raise Refused("DEADLINE")


def state_directory():
    # DynamicUser StateDirectory uses a root-owned link into /var/lib/private.
    # systemd sets WorkingDirectory to this exact service directory before exec.
    entry = os.lstat(STATE_PATH)
    if stat.S_ISLNK(entry.st_mode):
        require(entry.st_uid == 0 and os.readlink(STATE_PATH) in ("private/mrjam-forgejo-policy", "/var/lib/private/mrjam-forgejo-policy"), "UNSAFE_STATE")
    else:
        require(stat.S_ISDIR(entry.st_mode), "UNSAFE_STATE")
    expected = os.stat(STATE_PATH)
    directory = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    actual = os.fstat(directory)
    try:
        require((actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino), "WRONG_WORKING_DIRECTORY")
        require(actual.st_uid == os.getuid() and stat.S_IMODE(actual.st_mode) == 0o700, "UNSAFE_STATE")
        return directory
    except Exception:
        os.close(directory)
        raise


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("plan", "apply"):
        print('{"decision":"reject","code":"INVALID_INVOCATION"}')
        return 2
    signal.signal(signal.SIGALRM, _expired)
    signal.alarm(180)
    try:
        policy = validate_policy(document(POLICY_PATH))
        api = Transport(document(CREDENTIAL_PATH, credential=True))
        if sys.argv[1] == "plan":
            snapshot = observe(api, policy)
            result = {"decision": "plan", "plan": plan(policy, snapshot), "observation": snapshot}
        else:
            approved = document(PLAN_PATH)
            directory = state_directory()
            try:
                lock = os.open("reconcile.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
                try:
                    locked = os.fstat(lock)
                    require(stat.S_ISREG(locked.st_mode) and locked.st_uid == os.getuid() and locked.st_nlink == 1 and stat.S_IMODE(locked.st_mode) == 0o600, "UNSAFE_STATE")
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    def consume(plan_hash):
                        require(HEX.fullmatch(plan_hash) is not None, "INVALID_PLAN_HASH")
                        require(len(os.listdir(directory)) <= 4096, "REPLAY_JOURNAL_LIMIT")
                        try:
                            fd = os.open("used-" + plan_hash, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                            os.fsync(fd)
                            os.close(fd)
                            os.fsync(directory)
                        except FileExistsError:
                            raise Refused("PLAN_ALREADY_USED") from None
                    result = apply(api, policy, approved, consume=consume)
                finally:
                    os.close(lock)
            finally:
                os.close(directory)
        result["authority"] = "unverified_observation"
        print(canonical(result).decode("ascii"))
        return 0
    except Refused as error:
        print(canonical({"decision": "reject", "code": error.code, "may_have_partial_changes": sys.argv[1] == "apply"}).decode("ascii"))
        return 2
    except Exception:
        print('{"decision":"reject","code":"CONTROLLER_FAILED","may_have_partial_changes":true}')
        return 2
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
