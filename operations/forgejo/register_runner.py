#!/usr/bin/env python3
"""Register exactly one repository-scoped coordinator using local credentials.

No CLI arguments or endpoint/command/path inputs exist. This is a separate
administrative identity from the runner, worker and candidate. The generated
token is kept locally and supplied to the daemon only by systemd LoadCredential.
No registration token appears in argv, logs or a Nix store path.
"""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys

_spec = importlib.util.spec_from_file_location("reconcile", Path(__file__).with_name("reconcile.py"))
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)
BASE = "/api/v1/repos/MrJ-am/mrjam-validation"
RUNNERS = BASE + "/actions/runners"
NAME = "mrjam-validation-controller"
STATE = "/var/lib/mrjam-forgejo-registration"
POLICY = "/etc/mrjam-forgejo-registration/policy.json"
CREDENTIAL = "/run/credentials/mrjam-forgejo-registration.service/forgejo-token"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class Transport(api.Transport):
    def endpoint_allowed(self, method, path):
        if method == "GET" and path in ("/api/v1/version", BASE, BASE + "/branches/main", BASE + "/branch_protections/main", RUNNERS):
            return True
        if method == "POST" and path == RUNNERS:
            return True
        return method == "GET" and re.fullmatch(re.escape(RUNNERS) + r"/[1-9][0-9]{0,17}", path) is not None


def validate_policy(value):
    api.exact(value, ("rules_revision",))
    api.require(type(value["rules_revision"]) is str and api.COMMIT.fullmatch(value["rules_revision"]), "INVALID_REVISION")
    return value


def prerequisites(transport, policy):
    api.require(transport.request("GET", "/api/v1/version") == {"version": api.VERSION}, "UNSUPPORTED_VERSION")
    repo = transport.request("GET", BASE)
    api.require(type(repo) is dict and repo.get("full_name") == "MrJ-am/mrjam-validation"
                and type(repo.get("id")) is int and repo["id"] > 0
                and repo.get("archived") is False and repo.get("mirror") is False
                and repo.get("default_branch") == "main" and repo.get("empty") is False, "WRONG_REPOSITORY")
    branch = transport.request("GET", BASE + "/branches/main")
    api.require(type(branch) is dict and branch.get("name") == "main" and type(branch.get("commit")) is dict
                and branch["commit"].get("id") == policy["rules_revision"], "UNQUALIFIED_RULES_HEAD")
    protection = api.filter_protection(transport.request("GET", BASE + "/branch_protections/main"))
    api.require(protection == api.desired_protection(), "UNQUALIFIED_PROTECTION")
    return repo["id"]


def identity(value):
    api.exact(value, ("id", "uuid", "repository_id", "rules_revision"))
    api.require(type(value["id"]) is int and 0 < value["id"] < 10**18
                and type(value["repository_id"]) is int and value["repository_id"] > 0
                and type(value["uuid"]) is str and UUID.fullmatch(value["uuid"])
                and type(value["rules_revision"]) is str and api.COMMIT.fullmatch(value["rules_revision"]), "INVALID_REGISTRATION")
    return value


def verify_remote(raw, expected):
    api.require(type(raw) is dict and raw.get("id") == expected["id"] and raw.get("uuid") == expected["uuid"]
                and raw.get("repo_id") == expected["repository_id"] and raw.get("owner_id") == 0
                and raw.get("name") == NAME and raw.get("ephemeral") is False, "REGISTRATION_CHANGED")


def register(transport, policy, existing, persist):
    validate_policy(policy)
    repo_id = prerequisites(transport, policy)
    if existing is not None:
        expected = identity(existing)
        api.require(expected["repository_id"] == repo_id and expected["rules_revision"] == policy["rules_revision"], "REGISTRATION_CHANGED")
        verify_remote(transport.request("GET", RUNNERS + "/" + str(expected["id"])), expected)
        return {"decision": "no-changes", "repository": "mrjam-validation", "runner_id": expected["id"], "rules_revision": policy["rules_revision"]}
    runners = transport.request("GET", RUNNERS)
    api.require(type(runners) is list, "RUNNER_INVENTORY_UNQUALIFIED")
    # Requiring an empty first page avoids inferring completeness from a server
    # pagination limit. Any pre-existing runner requires a separate adoption.
    api.require(runners == [], "EXISTING_REGISTRATION_REQUIRES_ADOPTION")
    # Recheck immediately before the only mutation. The administrative identity
    # must additionally be serialized against other authorized control planes.
    api.require(prerequisites(transport, policy) == repo_id, "REGISTRATION_CHANGED")
    result = transport.request("POST", RUNNERS, {"name": NAME, "description": "MRJ.am fixed validation coordinator", "ephemeral": False})
    api.require(type(result) is dict and set(result) == {"id", "uuid", "token"}, "INVALID_REGISTRATION")
    expected = identity({"id": result["id"], "uuid": result["uuid"], "repository_id": repo_id, "rules_revision": policy["rules_revision"]})
    token = result["token"]
    api.require(type(token) is str and re.fullmatch(r"[A-Za-z0-9_-]{20,256}", token), "INVALID_CREDENTIAL")
    verify_remote(transport.request("GET", RUNNERS + "/" + str(expected["id"])), expected)
    persist(expected, token)
    return {"decision": "registered", "repository": "mrjam-validation", "runner_id": expected["id"], "rules_revision": policy["rules_revision"]}


def configuration(metadata):
    identity(metadata)
    return {
        "log": {"level": "error", "job_level": "error"},
        "runner": {"capacity": 1, "envs": {}, "env_file": "/dev/null", "timeout": "31m", "shutdown_timeout": "32m", "insecure": False, "fetch_timeout": "10s", "fetch_interval": "5s", "report_interval": "2s", "labels": []},
        "cache": {"enabled": False},
        "container": {"privileged": False, "valid_volumes": [], "docker_host": "-"},
        "host": {"workdir_parent": "/var/lib/mrjam-forgejo-runner/work"},
        "server": {"connections": {"mrjam-validation": {"url": "http://127.0.0.1:3004", "uuid": metadata["uuid"],
            "token_url": "file:$CREDENTIALS_DIRECTORY/runner-token", "labels": ["mrjam-controller:host"]}}},
    }


def store(root, metadata, token):
    # A partial registration is intentionally not overwritten or recreated.
    # Operator recovery can revoke only the recorded runner ID, after review.
    os.mkdir(".new-registration", 0o700, dir_fd=root)
    directory = os.open(".new-registration", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
    try:
        for name, value in (("identity.json", api.canonical(metadata) + b"\n"), ("runner-token", token.encode("ascii") + b"\n"), ("connection.json", api.canonical(configuration(metadata)) + b"\n")):
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=directory)
            try:
                api.require(os.write(fd, value) == len(value), "REGISTRATION_STORAGE_FAILED")
                os.fsync(fd)
            finally:
                os.close(fd)
        os.fsync(directory)
    finally:
        os.close(directory)
    os.rename(".new-registration", "registration", src_dir_fd=root, dst_dir_fd=root)
    os.fsync(root)


def main():
    root = lock = None
    try:
        api.require(len(sys.argv) == 1 and os.getuid() != 0, "INVALID_INVOCATION")
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(api.Refused("DEADLINE_EXCEEDED")))
        signal.alarm(120)
        policy = validate_policy(api.document(POLICY))
        token = api.document(CREDENTIAL, credential=True)
        root = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(root)
        api.require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, "UNSAFE_REGISTRATION_STATE")
        lock = os.open("operation.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=root)
        info = os.fstat(lock)
        api.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600, "UNSAFE_REGISTRATION_STATE")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        names = set(os.listdir(root))
        api.require(names <= {"operation.lock", "registration"}, "INCOMPLETE_REGISTRATION")
        existing = None
        if "registration" in names:
            directory = os.open("registration", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            try:
                info = os.fstat(directory)
                api.require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700
                            and set(os.listdir(directory)) == {"identity.json", "runner-token", "connection.json"}, "UNSAFE_REGISTRATION_STATE")
            finally:
                os.close(directory)
            existing = identity(api.document(STATE + "/registration/identity.json"))
            api.document(STATE + "/registration/runner-token", credential=True)
            api.require(api.document(STATE + "/registration/connection.json") == configuration(existing), "REGISTRATION_CHANGED")
        result = register(Transport(token), policy, existing, lambda record, secret: store(root, record, secret))
        print(json.dumps({**result, "authority": "unverified_observation"}, sort_keys=True, separators=(",", ":")))
        return 0
    except api.Refused as error:
        print(json.dumps({"decision": "reject", "code": error.code}, separators=(",", ":")))
        return 2
    except Exception:
        print('{"decision":"reject","code":"REGISTRATION_FAILED"}')
        return 2
    finally:
        if lock is not None:
            os.close(lock)
        if root is not None:
            os.close(root)


if __name__ == "__main__":
    raise SystemExit(main())
