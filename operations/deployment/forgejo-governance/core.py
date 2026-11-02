"""Closed initial source adoption and main protection; no executable CLI yet.

The package must seal a separately reviewed binding before enabling an entry.
Existing refs/visibility are preserved, source refs are archived by bundle hash,
and main can only fast-forward. Existing protections are never bypassed.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

import reconcile
import credentials

NAMES = tuple(sorted(reconcile.REPOSITORIES))
PRIVATE_SOURCES = frozenset(("Signature", "matheval", "mrjam-plateforme", "mrjam-validation", "vision"))
OID = re.compile(r"[0-9a-f]{40}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
STATE = Path("/var/lib/mrjam-forgejo-bootstrap")
STAGING = Path("/var/lib/mrjam-source-import")


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def valid_ref(value):
    return (type(value) is str and len(value) <= 512 and value.startswith(("refs/heads/", "refs/tags/"))
            and re.fullmatch(r"[A-Za-z0-9_./-]+", value) is not None
            and not any(part in value for part in ("..", "//", "@{"))
            and all(part and not part.startswith(".") and not part.endswith((".", ".lock")) for part in value.split("/")))


def parse_refs(raw):
    require(type(raw) is bytes and len(raw) <= 4*1024*1024, "REFERENCE_LIMIT")
    result = {}
    try:
        for line in raw.decode("ascii").splitlines():
            oid, ref = line.split("\t", 1)
            require(OID.fullmatch(oid) and valid_ref(ref) and ref not in result, "REFERENCE_SHAPE_REFUSED")
            result[ref] = oid
    except (UnicodeError, ValueError):
        raise Refused("REFERENCE_SHAPE_REFUSED") from None
    require(len(result) <= 4096, "REFERENCE_LIMIT")
    return result


class Binding:
    def __init__(self, raw, expected_sha256):
        require(type(raw) is bytes and len(raw) <= 2*1024*1024 and type(expected_sha256) is str
                and HEX.fullmatch(expected_sha256) and hashlib.sha256(raw).hexdigest() == expected_sha256,
                "BINDING_HASH_REFUSED")
        # reconcile's parser has a deliberately smaller API-document bound.
        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result, "BINDING_DUPLICATE_KEY")
                result[key] = value
            return result
        value = json.loads(raw, object_pairs_hook=pairs)
        require(type(value) is dict and set(value) == {"schema_version", "owner", "forgejo_version",
                "rules_revision", "controller_revision", "repositories", "metadata_disposition"}, "BINDING_FIELDS_REFUSED")
        require(type(value["schema_version"]) is int and value["schema_version"] == 1
                and value["owner"] == "MrJ-am" and value["forgejo_version"] == "17.0.1", "BINDING_TARGET_REFUSED")
        require(all(type(value[k]) is str and OID.fullmatch(value[k]) for k in ("rules_revision", "controller_revision")),
                "BINDING_REVISION_REFUSED")
        require(value["metadata_disposition"] == "existing-forgejo-preserved-github-lfs-and-collaboration-retained",
                "BINDING_METADATA_DISPOSITION_REFUSED")
        repos = value["repositories"]
        require(type(repos) is dict and tuple(sorted(repos)) == NAMES, "BINDING_REPOSITORIES_REFUSED")
        for name, repo in repos.items():
            require(type(repo) is dict and set(repo) == {"source", "bundle", "bundle_sha256", "refs_sha256", "main"},
                    "BINDING_SOURCE_FIELDS_REFUSED")
            require(type(repo["main"]) is str and OID.fullmatch(repo["main"]), "BINDING_MAIN_REFUSED")
            require(repo["source"] == "reviewed-bundle" and repo["bundle"] == str(STAGING/(name+".bundle"))
                    and type(repo["bundle_sha256"]) is str and HEX.fullmatch(repo["bundle_sha256"]),
                    "BINDING_BUNDLE_REFUSED")
            require(type(repo["refs_sha256"]) is str and HEX.fullmatch(repo["refs_sha256"]), "BINDING_REFS_REFUSED")
        require(repos["mrjam-validation"]["main"] == value["rules_revision"], "BINDING_RULES_REFUSED")
        # The orphan used by the synthetic complete-chain fixture is expressly
        # not an accepted production rules history.
        require(value["rules_revision"] != "93bd67666a3b4be9657c333931fa25b2359e165b", "SYNTHETIC_RULES_REFUSED")
        self.value, self.digest = value, expected_sha256
        self.repositories = repos

    def policy(self, phase):
        return reconcile.validate_policy({"schema_version": 2, "owner": "MrJ-am", "forgejo_version": "17.0.1",
            "rules_revision": self.value["rules_revision"], "controller_revision": self.value["controller_revision"],
            "phase": phase, "repositories": list(NAMES)})


def verify_bundle_file(path, expected, *, owner=0, stage_root=STAGING):
    path = Path(path)
    require(path.parent == stage_root and path.name in {name+".bundle" for name in NAMES}, "BUNDLE_PATH_REFUSED")
    for parent in (*reversed(stage_root.parents), stage_root):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner and not info.st_mode & 0o022,
                "BUNDLE_DIRECTORY_REFUSED")
    require(stat.S_IMODE(stage_root.lstat().st_mode) == 0o700, "BUNDLE_DIRECTORY_REFUSED")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == owner and before.st_nlink == 1
                and stat.S_IMODE(before.st_mode) in (0o400,0o600) and 0 < before.st_size <= 64*1024**3,
                "BUNDLE_FILE_REFUSED")
        require(hashlib.file_digest(stream, "sha256").hexdigest() == expected, "BUNDLE_HASH_REFUSED")
        after = os.fstat(stream.fileno())
        require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)
                == (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns), "BUNDLE_CHANGED")


def verify_source_inputs(binding):
    for source in binding.repositories.values():
        verify_bundle_file(source["bundle"], source["bundle_sha256"])
    return {"schema_version":1, "binding_sha256":binding.digest, "source_inputs_verified":True}


def target_refs(source, refs):
    """Archive original branch/tag names without replacing any existing ref."""
    result = {"refs/heads/main": source["main"]}
    if source["source"] == "reviewed-bundle":
        prefix = "github-import/" + source["bundle_sha256"][:16] + "/"
        for ref, oid in refs.items():
            namespace, name = ("refs/heads/", ref[11:]) if ref.startswith("refs/heads/") else ("refs/tags/", ref[10:])
            result[namespace + prefix + name] = oid
    require(all(valid_ref(ref) for ref in result), "ARCHIVE_REFERENCE_LIMIT")
    return result


def import_plan(before, wanted, ancestor):
    for ref, oid in wanted.items():
        if ref in before and before[ref] != oid:
            require(ref == "refs/heads/main" and ancestor(before[ref], oid), "EXISTING_REFERENCE_CONFLICT")
    return {ref: oid for ref, oid in wanted.items() if before.get(ref) != oid}


class Git:
    def __init__(self, executable, credential_helper, *, run=subprocess.run):
        self.executable, self.credential_helper, self.run = executable, credential_helper, run

    def command(self, arguments, *, accepted=(0,), timeout=120):
        env = {"HOME": "/nonexistent", "XDG_CONFIG_HOME": "/nonexistent", "LANG": "C", "LC_ALL": "C",
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
               "GIT_ALLOW_PROTOCOL": "file:http", "GIT_NO_LAZY_FETCH": "1", "GIT_NO_REPLACE_OBJECTS": "1",
               "GIT_OPTIONAL_LOCKS": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
        prefix = [self.executable, "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                  "-c", "gc.auto=0", "-c", "transfer.fsckObjects=true", "-c", "fetch.fsckObjects=true",
                  "-c", "http.proxy=", "-c", "http.followRedirects=false",
                  "-c", "credential.helper=", "-c", "credential.helper=" + self.credential_helper,
                  "-c", "credential.useHttpPath=true"]
        result = self.run(prefix+arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env=env, timeout=timeout, check=False)
        require(result.returncode in accepted and len(result.stdout) <= 4*1024*1024, "GIT_OPERATION_REFUSED")
        return result

    def remote_refs(self, name):
        return parse_refs(self.command(["ls-remote", "--refs", self.url(name), "refs/heads/*", "refs/tags/*"]).stdout)

    @staticmethod
    def url(name):
        require(name in NAMES, "REPOSITORY_REFUSED")
        return "http://127.0.0.1:3004/MrJ-am/" + name + ".git"

    def adopt(self, name, source, token):
        with credentials.broker(token, name), tempfile.TemporaryDirectory(prefix="source-adoption-", dir=STATE) as directory:
            path = str(Path(directory)/"objects.git")
            self.command(["init", "--bare", "--initial-branch=main", path])
            if source["source"] == "reviewed-bundle":
                bundle = Path(source["bundle"])
                with bundle.open("rb") as stream:
                    require(hashlib.file_digest(stream, "sha256").hexdigest() == source["bundle_sha256"], "BUNDLE_HASH_REFUSED")
                # Verify in the EMPTY repository: bundle prerequisites must not
                # be satisfied accidentally by the destination's private history.
                self.command(["-C", path, "bundle", "verify", str(bundle)], timeout=600)
                raw = self.command(["-C", path, "bundle", "list-heads", str(bundle)]).stdout
                heads = parse_refs(b"\n".join(line.replace(b" ", b"\t", 1) for line in raw.splitlines()))
                require(hashlib.sha256(reconcile.canonical(heads)).hexdigest() == source["refs_sha256"],
                        "BUNDLE_REFERENCES_CHANGED")
                wanted = target_refs(source, heads)
            before = self.remote_refs(name)
            if before:
                # All existing objects stay private on this host. This fetch
                # establishes ancestry, and never returns repository contents.
                self.command(["-C", path, "fetch", "--no-tags", "--no-recurse-submodules", self.url(name),
                              "refs/heads/*:refs/heads/existing/*", "refs/tags/*:refs/tags/existing/*"], timeout=600)
            if source["source"] == "reviewed-bundle":
                self.command(["-C", path, "fetch", "--no-tags", "--no-recurse-submodules", str(bundle),
                              "refs/heads/*:refs/heads/source/*", "refs/tags/*:refs/tags/source/*"], timeout=600)
            self.command(["-C", path, "cat-file", "-e", source["main"]+"^{commit}"])
            def ancestor(old, new):
                return self.command(["-C", path, "merge-base", "--is-ancestor", old, new], accepted=(0,1)).returncode == 0
            plan = import_plan(before, wanted, ancestor)
            require(self.remote_refs(name) == before, "REFERENCE_OBSERVATION_CHANGED")
            if plan:
                # No plus refspec, force, delete, mirror, prune, checkout, hook
                # bypass or change of an existing protected-branch rule.
                self.command(["-C", path, "push", "--atomic", self.url(name),
                              *(oid+":"+ref for ref, oid in sorted(plan.items()))], timeout=600)
            require(self.remote_refs(name) == {**before, **wanted}, "REFERENCE_READBACK_FAILED")


def reconcile_phase(api, binding, phase, consumed):
    policy = binding.policy(phase)
    snapshot = reconcile.observe(api, policy)
    def consume(digest):
        require(digest not in consumed, "RECONCILE_PLAN_REPLAY")
        path = STATE/("source-plan-"+digest)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        consumed.add(digest)
    for attempt in range(3):
        plan = reconcile.plan(policy, snapshot)
        count = len(consumed)
        try:
            return reconcile.apply(api, policy, plan, consume=consume)
        except reconcile.Refused as error:
            # An existing repository may finish its own post-receive update
            # between the read and the reconciler's pre-write CAS. Only accept
            # the demonstrated is_empty true -> false transition, before any
            # plan was consumed or mutation made. Every other drift is fatal.
            require(phase == "bootstrap-repositories" and error.code == "STALE_OR_CHANGED_PLAN"
                    and len(consumed) == count and attempt < 2, "RECONCILIATION_DRIFT_REFUSED")
            api = reconcile.Transport(api.token)
            following = reconcile.observe(api, policy)
            expected = json.loads(json.dumps(snapshot))
            transitions = 0
            for name, row in expected["repositories"].items():
                observed = following["repositories"][name]
                if row is not None and observed is not None and row["empty"] is True and observed["empty"] is False:
                    row["empty"] = False
                    transitions += 1
            require(transitions > 0 and expected == following, "RECONCILIATION_DRIFT_REFUSED")
            snapshot = following


class InitialTransport(reconcile.Transport):
    def endpoint_allowed(self, method, path):
        return (method == "GET" and path == "/api/v1/orgs/MrJ-am") or (
            method == "POST" and path == "/api/v1/orgs") or super().endpoint_allowed(method, path)


def ensure_organization(api):
    # Fixed initial namespace only; do not rename or convert a personal user,
    # change existing members, enumerate identities, or reset any credential.
    organization = api.request("GET", "/api/v1/orgs/MrJ-am", missing=True)
    if organization is None:
        api.request("POST", "/api/v1/orgs", {"username": "MrJ-am", "visibility": "private"})
        organization = api.request("GET", "/api/v1/orgs/MrJ-am")
    require(type(organization) is dict and organization.get("username") == "MrJ-am"
            and type(organization.get("id")) is int and organization["id"] > 0, "ORGANIZATION_IDENTITY_REFUSED")


def wait_repository_metadata(api, binding, original, *, sleep=time.sleep):
    # Forgejo's post-receive worker updates is_empty asynchronously after Git
    # has acknowledged the atomic push. Observe its real convergence before
    # asking the existing reconciler to protect a nonempty main; never patch
    # the database or manufacture that metadata ourselves. Eight full reads
    # stay within Transport's 160-request budget (8 * 19 requests).
    for attempt in range(8):
        observed = reconcile.observe(api, binding.policy("protect-main"))["repositories"]
        require(all(row is not None and row["id"] == original[name]["id"]
                    and row["private"] == original[name]["private"] for name, row in observed.items()),
                "REPOSITORY_IDENTITY_CHANGED")
        if all(row["empty"] is False for row in observed.values()):
            return
        if attempt != 7:
            sleep(5)
    raise Refused("SOURCE_METADATA_NOT_CONVERGED")


def adopt(binding, git, bootstrap):
    # The bootstrap lock spans all repository operations and token lifetime.
    # Per-repository writes are atomic; the cutover's paired snapshot is the
    # all-repository return boundary before any public write is reopened.
    with bootstrap.governance_lease() as token:
        ensure_organization(InitialTransport(token))
        api = reconcile.Transport(token)
        consumed = set()
        reconcile_phase(api, binding, "bootstrap-repositories", consumed)
        original = reconcile.observe(reconcile.Transport(token),binding.policy("bootstrap-repositories"))["repositories"]
        require(all(row is not None for row in original.values()),"SOURCE_REPOSITORY_MISSING")
        require(all(original[name]["private"] is True for name in PRIVATE_SOURCES),"PRIVATE_SOURCE_PUBLIC_TARGET_REFUSED")
        for name in NAMES:
            git.adopt(name, binding.repositories[name], token)
        wait_repository_metadata(reconcile.Transport(token),binding,original)
        reconcile_phase(reconcile.Transport(token), binding, "protect-main", consumed)
        api = reconcile.Transport(token)
        snapshot = reconcile.observe(api, binding.policy("protect-main"))
        require(all(repo is not None and repo["empty"] is False and repo["actions_enabled"] is False
                    and repo["protection"] == reconcile.desired_protection()
                    for repo in snapshot["repositories"].values()), "PROTECTED_POLICY_READBACK_FAILED")
        require(reconcile.observe_rules_head(api, binding.policy("protect-main")) == binding.value["rules_revision"],
                "RULES_MAIN_CHANGED")
    # Only after the lease context has verified token revocation.
    return {"schema_version": 1, "binding_sha256": binding.digest, "sources_bound": True,
            "protected_policy_verified": True, "temporary_credentials_revoked": True}


if __name__ == "__main__":
    raise SystemExit(64)
