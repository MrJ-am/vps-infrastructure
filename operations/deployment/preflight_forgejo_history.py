#!/usr/bin/env python3
"""Nine fixed bare repositories: existence and commit metadata, never content.

No API credential, network, git fetch, checkout, arbitrary path or ref output.
Existing repository locations follow the received repository.ROOT configuration.
"""
import json
import os
from pathlib import Path
import resource
import stat
import subprocess
import sys
import time

GIT = "/nix/store/nly4cml071i82515r89rpdw38z55wjqd-git-2.54.0/bin/git"
ROOT = Path("/var/lib/forgejo/repositories/mrj-am")
EXPECTED = {
    "Signature": {"audition_log_source": "17194087eec9162bb5372221c43e1de0501dfe6a",
                  "vision_source": "17495b13cefa24473e37434b98336b27caec8cdf"},
    "apprendre-a-demontrer": {"observed_github_main": "a2690c7cd6a706cada866e4aa576819c4ed20092"},
    "etp-vie-affective": {"observed_github_main": "65bbd8c53a1f6d2efda453a5c82d66c49df26699"},
    "matheval": {"qualified_frontend": "91b5b33541a39faade0c40792bfed5ad35ae80a1"},
    "mrjam-plateforme": {"published_identity": "2a34dac722ff1dab9a63aec56e407dd996de0719"},
    "mrjam-validation": {"reviewed_rules_source": "eb71ffe5944943474c5ee483e66c270b5976ab90"},
    "style-mrjam": {"observed_github_main": "2c145fb82a141d0a9a8b552577998852f574b788"},
    "vision": {"published_workers": "61cf80bddc5e1f6e7b330af319e0c9ecf742dc93"},
    "vps-infrastructure": {"observed_github_main": "b9621e4e9b1c42648f822962622bdc64d297f38a",
                           "published_preflight": "25d32b706d60116fe18bd8a8c63247d5dd57d6d7"},
}


def require(value):
    if not value:
        raise ValueError()


def fixed_directory(path):
    for parent in (*reversed(path.parents), path):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0, 982)
                and not info.st_mode & 0o002)


def historical_tree(path, *, owners=(0, 982), clock=time.monotonic):
    """Only lstat/scandir metadata, with no following of any repository link."""
    deadline = clock() + 20
    count = 0
    stack = [path/"objects", path/"refs", path/"HEAD", path/"config"]
    if (path/"packed-refs").exists() or (path/"packed-refs").is_symlink():
        stack.append(path/"packed-refs")
    while stack:
        current = stack.pop()
        info = current.lstat()
        count += 1
        require(count <= 200000 and clock() < deadline and info.st_uid in owners and not info.st_mode & 0o002)
        require(stat.S_ISDIR(info.st_mode) or (stat.S_ISREG(info.st_mode) and info.st_nlink == 1))
        if stat.S_ISDIR(info.st_mode):
            with os.scandir(current) as directory:
                for entry in directory:
                    require(count+len(stack) < 200000 and clock() < deadline)
                    stack.append(Path(entry.path))


def inspect_repository(path, commits, *, git=GIT, run=subprocess.run, validate=fixed_directory, tree_validate=historical_tree):
    empty = {"exists": False, "bare": None, "non_empty": None, "main_exists": None,
             "history_indirection_absent": None, "expected_commits_present": {label: None for label in commits},
             "expected_commits_in_main": {label: None for label in commits}}
    try:
        path.lstat()
    except FileNotFoundError:
        return empty
    empty["exists"] = True
    validate(path)
    tree_validate(path)
    # Refuse object indirection and partial histories. No alternate object path
    # or promisor helper can cause an unrequested read or network access.
    for suffix in ("objects/info/alternates", "objects/info/http-alternates", "commondir", "shallow"):
        target = path / suffix
        if target.exists() or target.is_symlink():
            empty["history_indirection_absent"] = False
            return empty
    for suffix in ("objects", "objects/pack", "refs"):
        validate(path / suffix)
    if any(child.name.endswith(".promisor") for child in (path/"objects/pack").iterdir()):
        empty["history_indirection_absent"] = False
        return empty
    env = {"HOME": "/nonexistent", "XDG_CONFIG_HOME": "/nonexistent", "LANG": "C", "LC_ALL": "C",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
           "GIT_ALLOW_PROTOCOL": "", "GIT_NO_LAZY_FETCH": "1", "GIT_NO_REPLACE_OBJECTS": "1",
           "GIT_OPTIONAL_LOCKS": "0"}
    prefix = [git, "-c", "safe.directory=" + str(path), "-c", "core.fsmonitor=false",
              "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=", "--git-dir=" + str(path)]
    def check(arguments, accepted=(0,)):
        response = run(prefix + arguments, env=env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=False)
        require(response.returncode in accepted and len(response.stdout) <= 16)
        return response
    require(check(["rev-parse", "--is-bare-repository"]).stdout == b"true\n")
    empty.update(bare=True, history_indirection_absent=True,
                 non_empty=check(["show-ref", "--quiet"], (0, 1)).returncode == 0,
                 main_exists=check(["show-ref", "--verify", "--quiet", "refs/heads/main"], (0, 1)).returncode == 0)
    for label, commit in commits.items():
        present = check(["cat-file", "-e", commit + "^{commit}"], (0, 1, 128)).returncode == 0
        empty["expected_commits_present"][label] = present
        empty["expected_commits_in_main"][label] = (
            check(["merge-base", "--is-ancestor", commit, "refs/heads/main"], (0, 1)).returncode == 0
            if present and empty["main_exists"] else False)
    return empty


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0:
        return 64
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    result = {}
    for name, commits in EXPECTED.items():
        try:
            result[name] = {"code": "OBSERVED", **inspect_repository(ROOT / (name.lower() + ".git"), commits)}
        except Exception:
            result[name] = {"code": "HISTORY_OBSERVATION_REFUSED"}
    print(json.dumps({"schema_version": 1, "code": "FORGEJO_HISTORY_OBSERVED", "repositories": result,
                      "repository_content_returned": False, "production_mutation": False,
                      "network_used": False}, sort_keys=True, separators=(",", ":")))
    return 0 if all(value["code"] == "OBSERVED" for value in result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
