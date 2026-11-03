"""Prepare one exact bootstrap PR. No review, status, merge or policy mutation."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

import credentials
import lease
import protection
import reconcile

REPO = "mrjam-validation"
BASE = "/api/v1/repos/MrJ-am/" + REPO
URL = "http://127.0.0.1:3004/MrJ-am/mrjam-validation.git"
WORKFLOW = ".forgejo/workflows/independent-validation.yml"
INPUT = Path("/var/lib/mrjam-ci-rules-proposal/proposal.bundle")
STATE = Path("/var/lib/mrjam-ci-rules-proposal")
TITLE = "Amorcer le workflow de validation indépendant"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


class Binding:
    def __init__(self, raw, expected_sha256):
        require(type(raw) is bytes and len(raw) <= 8192
                and hashlib.sha256(raw).hexdigest() == expected_sha256, "BINDING_HASH_REFUSED")
        value = reconcile.parse(raw)
        require(type(value) is dict and set(value) == {"schema_version","base","head","tree",
            "workflow_sha256","bundle_sha256","bundle_bytes","evidence_sha256"}, "BINDING_SHAPE_REFUSED")
        require(type(value["schema_version"]) is int and value["schema_version"] == 1, "BINDING_SHAPE_REFUSED")
        for name in ("base","head","tree"):
            require(type(value[name]) is str and HEX40.fullmatch(value[name]), "BINDING_REVISION_REFUSED")
        for name in ("workflow_sha256","bundle_sha256","evidence_sha256"):
            require(type(value[name]) is str and HEX64.fullmatch(value[name]), "BINDING_DIGEST_REFUSED")
        require(type(value["bundle_bytes"]) is int and 0 < value["bundle_bytes"] <= 1024**2
                and value["base"] != value["head"], "BINDING_SIZE_REFUSED")
        self.value = value
        self.branch = "bootstrap-ci-workflow-" + value["head"][:16]
        self.ref = "refs/heads/" + self.branch
        self.body = (
            "Cette proposition ajoute uniquement le workflow de validation déjà qualifié. "
            "Elle ne change aucune règle ni attente de test.\n\n"
            "La CI initiale n’est pas encore active : les preuves liées ci-dessous sont des "
            "vérifications hors CI, pas une exécution du workflow sur cette forge. "
            "Aucun statut de réussite, aucune revue ni fusion n’est créé par cet outil. "
            "La protection de main et l’approbation humaine restent requises.\n\n"
            "MRJAM-RULES-BOOTSTRAP-PROPOSAL-V1\n"
            "base="+value["base"]+"\nhead="+value["head"]+"\ntree="+value["tree"]+
            "\nworkflow_sha256="+value["workflow_sha256"]+
            "\nevidence_sha256="+value["evidence_sha256"]+"\n"
        )


class Transport(reconcile.Transport):
    def __init__(self, token, binding):
        super().__init__(token)
        self.binding = binding

    def endpoint_allowed(self, method, path):
        return (method == "GET" and path in (
            "/api/v1/version", "/api/v1/user", BASE, BASE+"/branches/main",
            BASE+"/branches/"+self.binding.branch,
            BASE+"/pulls/main/"+self.binding.branch)
            or method == "POST" and path == BASE+"/pulls")


def private_bundle(binding, reader):
    info = STATE.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0
            and stat.S_IMODE(info.st_mode) == 0o700, "PROPOSAL_DIRECTORY_REFUSED")
    raw = reader(INPUT, maximum=1024**2)
    require(len(raw) == binding.value["bundle_bytes"]
            and hashlib.sha256(raw).hexdigest() == binding.value["bundle_sha256"], "PROPOSAL_BUNDLE_REFUSED")
    # Bundle v2 has exactly one prerequisite and one advertised proposal ref.
    header = raw.split(b"\n\n",1)[0].splitlines()
    require(len(header) == 3 and header[0] == b"# v2 git bundle"
            and header[1].startswith(("-"+binding.value["base"]+" ").encode())
            and header[2] == (binding.value["head"]+" "+binding.ref).encode(), "PROPOSAL_BUNDLE_HEADER_REFUSED")
    return raw


class Git:
    def __init__(self, executable, credential_helper, hooks, binding, *, run=subprocess.run):
        self.executable, self.credential_helper, self.hooks, self.binding, self.run = executable, credential_helper, hooks, binding, run

    def command(self, arguments, *, accepted=(0,), timeout=90):
        # Same isolated Git environment as the qualified initial import. The
        # only hook is now our immutable create-only pre-push guard.
        env = {"HOME":"/nonexistent","XDG_CONFIG_HOME":"/nonexistent","LANG":"C","LC_ALL":"C",
            "GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null","GIT_TERMINAL_PROMPT":"0",
            "GIT_ALLOW_PROTOCOL":"file:http","GIT_NO_LAZY_FETCH":"1","GIT_NO_REPLACE_OBJECTS":"1",
            "GIT_OPTIONAL_LOCKS":"0","GIT_LFS_SKIP_SMUDGE":"1"}
        prefix = [self.executable,"-c","core.hooksPath="+self.hooks,"-c","core.fsmonitor=false",
            "-c","gc.auto=0","-c","maintenance.auto=false","-c","transfer.fsckObjects=true","-c","fetch.fsckObjects=true",
            "-c","http.proxy=","-c","http.followRedirects=false","-c","credential.helper=",
            "-c","credential.helper="+self.credential_helper,"-c","credential.useHttpPath=true"]
        result = self.run(prefix+arguments,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,env=env,timeout=timeout,check=False)
        require(result.returncode in accepted and len(result.stdout) <= 4*1024**2, "GIT_OPERATION_REFUSED")
        return result.stdout

    def refs(self):
        raw = self.command(["ls-remote","--refs",URL,"refs/heads/main",self.binding.ref])
        result = {}
        for line in raw.decode("ascii").splitlines():
            oid, separator, ref = line.partition("\t")
            require(separator and HEX40.fullmatch(oid) and ref in ("refs/heads/main",self.binding.ref)
                    and ref not in result, "REFERENCE_SHAPE_REFUSED")
            result[ref] = oid
        require(result.get("refs/heads/main") == self.binding.value["base"], "MAIN_CHANGED")
        require(result.get(self.binding.ref) in (None,self.binding.value["head"]), "PROPOSAL_BRANCH_CONFLICT")
        return result

    def prepare_and_push(self, raw):
        before = self.refs()
        with tempfile.TemporaryDirectory(prefix="private-proposal-",dir=STATE) as root:
            path = str(Path(root)/"objects.git")
            bundle = Path(root)/"proposal.bundle"
            bundle.write_bytes(raw); bundle.chmod(0o600)
            self.command(["init","--bare","--initial-branch=main",path])
            self.command(["-C",path,"fetch","--depth=1","--no-tags","--no-recurse-submodules",URL,
                "refs/heads/main:refs/heads/base"])
            self.command(["-C",path,"bundle","verify",str(bundle)])
            self.command(["-C",path,"fetch","--no-tags","--no-recurse-submodules",str(bundle),
                self.binding.ref+":refs/heads/proposal"])
            head, base = self.binding.value["head"], self.binding.value["base"]
            require(self.command(["-C",path,"rev-list","--parents","-n","1",head]).strip()
                    == (head+" "+base).encode(), "PROPOSAL_PARENT_REFUSED")
            require(self.command(["-C",path,"rev-parse",head+"^{tree}"]).strip()
                    == self.binding.value["tree"].encode(), "PROPOSAL_TREE_REFUSED")
            require(self.command(["-C",path,"diff-tree","--no-commit-id","--name-status","-r",
                "--no-renames","-z",base,head]) == b"A\0"+WORKFLOW.encode()+b"\0", "PROPOSAL_DELTA_REFUSED")
            entry = self.command(["-C",path,"ls-tree","-z",head,"--",WORKFLOW])
            require(re.fullmatch(rb"100644 blob [0-9a-f]{40}\t"+re.escape(WORKFLOW.encode())+rb"\x00",entry),
                    "WORKFLOW_MODE_REFUSED")
            require(hashlib.sha256(self.command(["-C",path,"show",head+":"+WORKFLOW])).hexdigest()
                    == self.binding.value["workflow_sha256"], "WORKFLOW_BYTES_REFUSED")
            require(self.refs() == before, "REFERENCE_OBSERVATION_CHANGED")
            if self.binding.ref not in before:
                self.command(["-C",path,"push","--atomic",URL,head+":"+self.binding.ref])
            after = self.refs()
            require(after == {"refs/heads/main":base,self.binding.ref:head}, "REFERENCE_READBACK_REFUSED")
        return self.binding.ref not in before


def observe(api, binding, bootstrap):
    require(api.request("GET","/api/v1/version") == {"version":"17.0.1"}, "FORGEJO_VERSION_REFUSED")
    me = api.request("GET","/api/v1/user")
    require(type(me) is dict and type(me.get("id")) is int and me["id"] > 0
            and me.get("login") == lease.ACCOUNT and me.get("is_admin") is True, "AUTHOR_IDENTITY_REFUSED")
    repo = api.request("GET",BASE)
    require(type(repo) is dict and type(repo.get("id")) is int and repo["id"] > 0
            and repo.get("full_name") == "MrJ-am/mrjam-validation" and repo.get("private") is True
            and repo.get("empty") is False and repo.get("archived") is False and repo.get("mirror") is False
            and repo.get("default_branch") == "main" and repo.get("has_actions") is False,
            "REPOSITORY_STATE_REFUSED")
    branch = api.request("GET",BASE+"/branches/main")
    require(type(branch) is dict and branch.get("name") == "main" and type(branch.get("commit")) is dict
            and branch["commit"].get("id") == binding.value["base"], "MAIN_CHANGED")
    protected = protection.verify(bootstrap)
    return {"repository_id":repo["id"],"author_id":me["id"],"protection_exact":protected}


def validate_pr(row, binding, observed):
    require(type(row) is dict and type(row.get("number")) is int and row["number"] > 0
            and row.get("state") == "open" and row.get("merged") is False
            and row.get("title") == TITLE and row.get("body") == binding.body,
            "PULL_REQUEST_CONFLICT")
    require(type(row.get("user")) is dict and row["user"].get("id") == observed["author_id"], "PULL_REQUEST_AUTHOR_REFUSED")
    for label, ref, sha in (("base","main",binding.value["base"]),("head",binding.branch,binding.value["head"])):
        part = row.get(label)
        require(type(part) is dict and part.get("ref") == ref and part.get("sha") == sha
                and type(part.get("repo")) is dict and part["repo"].get("id") == observed["repository_id"],
                "PULL_REQUEST_TARGET_REFUSED")
    return row["number"]


def open_proposal(binding, git, bootstrap, *, transport=Transport):
    raw = private_bundle(binding, bootstrap.private_file)
    with lease.repository_lease(bootstrap) as token:
        api = transport(token,binding)
        before = observe(api,binding,bootstrap)
        path = BASE+"/pulls/main/"+binding.branch
        previous = api.request("GET",path,missing=True)
        if previous is not None:
            validate_pr(previous,binding,before)
        with credentials.broker(token,REPO):
            branch_created = git.prepare_and_push(raw)
            require(observe(api,binding,bootstrap) == before, "REPOSITORY_OBSERVATION_CHANGED")
            if previous is None:
                # If an ambiguous HTTP result interrupted the earlier attempt,
                # the next invocation resolves the exact same PR by base/head.
                row = api.request("POST",BASE+"/pulls",{"base":"main","head":binding.branch,
                    "title":TITLE,"body":binding.body})
                number = validate_pr(row,binding,before)
            else:
                number = validate_pr(previous,binding,before)
            final = api.request("GET",path)
            require(validate_pr(final,binding,before) == number, "PULL_REQUEST_READBACK_REFUSED")
            require(git.refs() == {"refs/heads/main":binding.value["base"],binding.ref:binding.value["head"]},
                    "REFERENCE_READBACK_REFUSED")
            require(observe(api,binding,bootstrap) == before, "REPOSITORY_OBSERVATION_CHANGED")
    return {"schema_version":1,"code":"RULES_PROPOSAL_OPENED","branch_created":branch_created,
        "pull_request_created":previous is None,"pull_request":number,
        "url":"https://forge.mrj.am/MrJ-am/mrjam-validation/pulls/"+str(number),
        "base":binding.value["base"],"head":binding.value["head"],"tree":binding.value["tree"],
        "temporary_token_revoked":True,"main_changed":False,"protection_changed":False,
        "review_created":False,"status_created":False,"merged":False,"actions_activated":False}
