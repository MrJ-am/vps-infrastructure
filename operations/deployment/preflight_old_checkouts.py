#!/usr/bin/env python3
"""Seventeen catalogued old source checkouts: Git metadata only, never contents.

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
    bare = check(["rev-parse", "--is-bare-repository"]).stdout
    require(bare in (b"true\n", b"false\n"))
    empty.update(bare=bare == b"true\n", history_indirection_absent=True,
                 non_empty=check(["show-ref", "--quiet"], (0, 1)).returncode == 0,
                 main_exists=check(["show-ref", "--verify", "--quiet", "refs/heads/main"], (0, 1)).returncode == 0)
    for label, commit in commits.items():
        present = check(["cat-file", "-e", commit + "^{commit}"], (0, 1, 128)).returncode == 0
        empty["expected_commits_present"][label] = present
        empty["expected_commits_in_main"][label] = (
            check(["merge-base", "--is-ancestor", commit, "refs/heads/main"], (0, 1)).returncode == 0
            if present and empty["main_exists"] else False)
    return empty


# Mechanically derived only from the previously received 137 source paths.
# No directory enumeration under /root and no following of .git pointer files.
CHECKOUTS = (
    ("catalogue-01", '/root/mrjam-assemblages/185f9316d6b208f12ef8279a52947a9789ee870d/payload', 'vps-infrastructure'),
    ("catalogue-02", '/root/mrjam-assemblages/54988ca67567db04d2e064feae91d558f7bb25fb/payload', 'vps-infrastructure'),
    ("catalogue-03", '/root/mrjam-corrections/audition/9feac618022a310de4f61cf2ce992ebe35e2f6dc/payload', 'vps-infrastructure'),
    ("catalogue-04", '/root/mrjam-corrections/forgejo/95b33d038c5652b4d23d30b8ccee21b8989f06c8/payload', 'vps-infrastructure'),
    ("catalogue-05", '/root/mrjam-corrections/forgejo/ac739eedcffc32d2fba29f4ce5b124e6c291b642/payload', 'vps-infrastructure'),
    ("catalogue-06", '/root/mrjam-corrections/forgejo/cff7b9401bb65cc93973eae68499cd0e37ad465b/payload', 'vps-infrastructure'),
    ("catalogue-07", '/root/mrjam-corrections/forgejo/f79bcaddf7ddaa637350d04bec01d30629e49c29/payload', 'vps-infrastructure'),
    ("catalogue-08", '/root/mrjam-corrections/log-interface/5023f4ed3599827eeeeaa119d0babbc370c14d82/payload', 'vps-infrastructure'),
    ("catalogue-09", '/root/mrjam-corrections/nextcloud-php-security/ba49a07931a20e3730b2085b2a7922330acf1979/payload', 'vps-infrastructure'),
    ("catalogue-10", '/root/mrjam-corrections/nextcloud-sso/1cfa76edd667dd2cb54228919c329b72b6c49462/payload', 'vps-infrastructure'),
    ("catalogue-11", '/root/mrjam-corrections/reconnexion/08e1d2d87e6e3c3290171436f6f5fb2acb8b5147/payload', 'vps-infrastructure'),
    ("catalogue-12", '/root/mrjam-corrections/vision-mcp-configuration/178a781317f09bd6d588d3cde3177d35c11bb435/payload', 'vps-infrastructure'),
    ("catalogue-13", '/root/vision-bascule-preparations/008671ee6eedf8bcb983b7a0435732f43f630441/source', 'vps-infrastructure'),
    ("catalogue-14", '/root/vision-identite-amorcage-operations/25f685900a9b65cb7cef872f0b55bcb21e35567d/source', 'vps-infrastructure'),
    ("catalogue-15", '/root/vision-semantique/32a4c3d2ad0e39568fe16d7acdb2472a7f095fc2/source', 'vps-infrastructure'),
    ("catalogue-16", '/root/vision-semantique/32a4c3d2ad0e39568fe16d7acdb2472a7f095fc2/source/vendor/matheval', 'matheval'),
    ("catalogue-17", '/root/vision-semantique/32a4c3d2ad0e39568fe16d7acdb2472a7f095fc2/source/vendor/vision', 'vision'),
)


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0:
        return 64
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    result = {}
    for label, location, repository in CHECKOUTS:
        path = Path(location)/".git"
        try:
            if path.exists() and stat.S_ISREG(path.lstat().st_mode):
                result[label] = {"code":"GIT_POINTER_NOT_FOLLOWED", "repository":repository,
                                 "git_metadata_present":True}
            else:
                result[label] = {"code":"OBSERVED", "repository":repository,
                                 **inspect_repository(path, EXPECTED[repository])}
        except Exception:
            result[label] = {"code":"HISTORY_OBSERVATION_REFUSED", "repository":repository}
    print(json.dumps({"schema_version":1,"code":"CATALOGUED_CHECKOUT_HISTORY_OBSERVED", "checkouts":result,
                      "repository_content_returned":False,"production_mutation":False,"network_used":False},
                     sort_keys=True,separators=(",",":")))
    return 0 if all(v["code"] in ("OBSERVED","GIT_POINTER_NOT_FOLLOWED") for v in result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
