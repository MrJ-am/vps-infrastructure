#!/usr/bin/env python3
"""Prepare two pinned development components; never approve or deploy a release.

The default is a read-only plan. Network access requires --apply and is limited
to a depth-one fetch of the full commit recorded in each committed Git link.
No clone, branch lookup, recursive submodule update, reset, clean or force.
"""

from __future__ import annotations

import argparse
import configparser
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


URLS = {
    "serveur/components/vision": "https://forge.mrj.am/MrJ-am/vision.git",
    "serveur/components/mateval": "https://forge.mrj.am/MrJ-am/matheval.git",
}
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
MAX_OUTPUT = 8 * 1024 * 1024


class Refused(Exception):
    """A fixed diagnostic code, without Git output or configuration values."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Refused(code)


def object_id(kind: str, value: bytes) -> str:
    return hashlib.sha1(kind.encode() + b" " + str(len(value)).encode() + b"\0" + value).hexdigest()


def safe_path(value: str) -> bool:
    return (
        bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and all(ord(char) >= 32 and ord(char) != 127 for char in value)
        and all(part not in {"", ".", ".."} and part.lower() != ".git" for part in value.split("/"))
    )


def no_symlink(path: Path) -> None:
    for candidate in (path, *path.parents):
        require(not candidate.is_symlink(), "SYMLINK_PATH_REFUSED")


def parse_tree(raw: bytes) -> dict[str, tuple[str, str, str]]:
    require(not raw or raw.endswith(b"\0"), "INVALID_TREE_OUTPUT")
    result: dict[str, tuple[str, str, str]] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            header, name = record.split(b"\t", 1)
            mode, kind, oid = header.decode("ascii").split(" ")
            path = name.decode("utf-8")
        except (ValueError, UnicodeError) as error:
            raise Refused("INVALID_TREE_OUTPUT") from error
        require(safe_path(path) and path not in result and bool(HEX40.fullmatch(oid)), "INVALID_TREE_ENTRY")
        require((mode, kind) in {("100644", "blob"), ("100755", "blob"), ("120000", "blob"), ("160000", "commit")}, "INVALID_TREE_ENTRY")
        result[path] = (mode, kind, oid)
    return result


def parse_modules(raw: bytes) -> dict[str, str]:
    require(len(raw) <= 16_384 and b"\0" not in raw, "INVALID_GITMODULES")
    parser = configparser.RawConfigParser(interpolation=None, strict=True, delimiters=("=",))
    try:
        parser.read_string(raw.decode("utf-8"))
    except (UnicodeError, configparser.Error) as error:
        raise Refused("INVALID_GITMODULES") from error
    require(not parser.defaults(), "INVALID_GITMODULES")
    result: dict[str, str] = {}
    for section in parser.sections():
        require(bool(re.fullmatch(r'submodule "[A-Za-z0-9_./-]+"', section)), "INVALID_GITMODULES")
        require(set(parser[section]) == {"path", "url"}, "GITMODULES_OPTIONS_REFUSED")
        path, url = parser[section]["path"], parser[section]["url"]
        require(path not in result and URLS.get(path) == url, "GITMODULES_PATH_OR_URL_MISMATCH")
        result[path] = url
    require(result == URLS, "GITMODULE_SET_MISMATCH")
    return result


def git_environment() -> dict[str, str]:
    # Keep only externally supplied askpass/CA settings from Git's environment.
    # Neither their values nor subprocess output are printed or written to disk.
    allowed = {"GIT_ASKPASS", "GIT_SSL_CAINFO", "GIT_SSL_CAPATH"}
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_") or key in allowed}
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_ATTR_NOSYSTEM": "1",
        "LC_ALL": "C",
    })
    return env


class Git:
    def run(self, directory: Path, *arguments: str, allow_missing: bool = False) -> bytes:
        transport = ["--config-env=http.https://forge.mrj.am/.extraHeader=FORGEJO_HEADER"] if "FORGEJO_HEADER" in os.environ else []
        if arguments and arguments[0] == "fetch":
            require(bool(transport), "FORGEJO_AUTHORIZATION_HEADER_REQUIRED")
        command = [
            "git", *transport, "-c", "core.hooksPath=" + os.devnull,
            "-c", "core.fsmonitor=false", "-c", "credential.helper=",
            "-c", "credential.interactive=false", "-c", "protocol.allow=never",
            "-c", "protocol.https.allow=always", "-c", "http.followRedirects=false",
            "-c", "submodule.recurse=false", "-c", "fetch.recurseSubmodules=false",
            "-c", "fetch.fsckObjects=true", "-c", "transfer.fsckObjects=true",
            "-c", "gc.auto=0", "-c", "maintenance.auto=false",
            "-C", str(directory), *arguments,
        ]
        try:
            result = subprocess.run(command, env=git_environment(), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    check=False, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Refused("GIT_UNAVAILABLE_OR_TIMEOUT") from error
        require(len(result.stdout) <= MAX_OUTPUT and len(result.stderr) <= MAX_OUTPUT, "GIT_OUTPUT_TOO_LARGE")
        if allow_missing and result.returncode == 1:
            return b""
        require(result.returncode == 0, "GIT_COMMAND_FAILED")
        return result.stdout


def text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8").strip()
    except UnicodeError as error:
        raise Refused("INVALID_GIT_TEXT") from error


def validate_repository(git: Git, root: Path) -> None:
    no_symlink(root)
    no_symlink(root / ".git")
    require(root.is_dir(), "REPOSITORY_DIRECTORY_REQUIRED")
    top = Path(text(git.run(root, "rev-parse", "--show-toplevel")))
    require(top.resolve() == root.resolve(), "NESTED_OR_WRONG_REPOSITORY")
    require(text(git.run(root, "rev-parse", "--is-bare-repository")) == "false", "WORKTREE_REQUIRED")
    require(text(git.run(root, "rev-parse", "--show-object-format")) == "sha1", "SHA1_REPOSITORY_REQUIRED")
    # Never follow local include files, URL rewrites, custom filters or headers.
    keys = text(git.run(root, "config", "--local", "--no-includes", "--name-only", "--list")).lower().splitlines()
    forbidden = ("include.", "includeif.", "url.", "http.", "https.", "credential.", "filter.", "trace.", "trace2.")
    require(not any(key.startswith(forbidden) for key in keys), "LOCAL_GIT_TRANSPORT_CONFIGURATION_REFUSED")
    require(not any(key in {"extensions.partialclone", "core.sparsecheckout", "core.sparsecheckoutcone"}
                    or key.endswith((".promisor", ".partialclonefilter")) for key in keys),
            "PARTIAL_OR_SPARSE_REPOSITORY_REFUSED")
    git_dir = Path(text(git.run(root, "rev-parse", "--absolute-git-dir")))
    no_symlink(git_dir)
    no_symlink(git_dir / "config")
    common = Path(text(git.run(root, "rev-parse", "--git-common-dir")))
    common = common if common.is_absolute() else root / common
    no_symlink(common)
    no_symlink(common / "config")
    for relative in ("objects/info/alternates", "objects/info/http-alternates", "info/grafts"):
        no_symlink(common / relative)
        require(not (common / relative).exists(), "EXTERNAL_OBJECT_SOURCE_REFUSED")
    # Worktree-specific configuration can add filters/rewrites after config --local.
    require(not (git_dir / "config.worktree").exists(), "WORKTREE_CONFIGURATION_REFUSED")


def clean(git: Git, root: Path, *, superproject: bool) -> None:
    arguments = ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored=matching"]
    if superproject:
        arguments.append("--ignore-submodules=all")
    require(not git.run(root, *arguments), "SUPERPROJECT_NOT_CLEAN" if superproject else "COMPONENT_NOT_CLEAN")


def verify_remote(git: Git, root: Path, url: str) -> None:
    require(text(git.run(root, "remote")).splitlines() == ["origin"], "COMPONENT_REMOTE_SET_MISMATCH")
    values = text(git.run(root, "config", "--local", "--get-all", "remote.origin.url")).splitlines()
    require(values == [url], "COMPONENT_REMOTE_URL_MISMATCH")
    push = text(git.run(root, "config", "--local", "--get-all", "remote.origin.pushurl", allow_missing=True)).splitlines()
    require(not push or push == [url], "COMPONENT_REMOTE_URL_MISMATCH")


def verify_commit_tree(git: Git, root: Path, expected: str) -> str:
    require(bool(HEX40.fullmatch(expected)), "FULL_COMMIT_REQUIRED")
    commit = git.run(root, "cat-file", "commit", expected)
    require(object_id("commit", commit) == expected, "COMMIT_OBJECT_MISMATCH")
    first = commit.split(b"\n", 1)[0]
    require(first.startswith(b"tree "), "INVALID_COMMIT_TREE")
    tree = text(first[5:])
    require(bool(HEX40.fullmatch(tree)), "INVALID_COMMIT_TREE")
    tree_raw = git.run(root, "cat-file", "tree", tree)
    require(object_id("tree", tree_raw) == tree, "TREE_OBJECT_MISMATCH")
    entries = parse_tree(git.run(root, "ls-tree", "-r", "-z", "--full-tree", expected))
    require(all(mode in {"100644", "100755"} and kind == "blob" for mode, kind, _ in entries.values()), "COMPONENT_SYMLINK_OR_NESTED_GITLINK_REFUSED")
    return tree


@dataclass(frozen=True)
class Component:
    path: str
    url: str
    commit: str
    action: str
    tree: str | None = None


@dataclass(frozen=True)
class Plan:
    superproject_commit: str
    modules_blob: str
    components: tuple[Component, ...]


def component_state(git: Git, root: Path, path: str, url: str, commit: str) -> Component:
    target = root / path
    no_symlink(target)
    if not target.exists():
        return Component(path, url, commit, "initialize-fetch-checkout")
    require(target.is_dir(), "COMPONENT_DIRECTORY_REQUIRED")
    if not any(target.iterdir()):
        return Component(path, url, commit, "initialize-fetch-checkout")
    require((target / ".git").exists(), "NONEMPTY_COMPONENT_WITHOUT_GIT")
    validate_repository(git, target)
    verify_remote(git, target, url)
    clean(git, target, superproject=False)
    # Existing checkouts are inspected only; the bootstrap never moves their HEAD.
    current = text(git.run(target, "rev-parse", "--verify", "--quiet", "HEAD", allow_missing=True))
    if not current:
        # Resume only an empty repository carrying our unused initial branch.
        # A failed fetch never triggers removal of files or a forced reset.
        require(text(git.run(target, "symbolic-ref", "--quiet", "HEAD")) == "refs/heads/bootstrap-unused",
                "UNBORN_COMPONENT_NOT_BOOTSTRAP")
        require(all(entry.name == ".git" for entry in target.iterdir()), "COMPONENT_NOT_EMPTY")
        return Component(path, url, commit, "fetch-checkout-initialized-empty")
    require(current == commit, "COMPONENT_HEAD_MISMATCH")
    attached = text(git.run(target, "symbolic-ref", "--quiet", "HEAD", allow_missing=True))
    require(not attached, "COMPONENT_DETACHED_HEAD_REQUIRED")
    return Component(path, url, commit, "verify-only", verify_commit_tree(git, target, commit))


def make_plan(root: Path, git: Git | None = None) -> Plan:
    git = git or Git()
    root = root.absolute()
    validate_repository(git, root)
    no_symlink(root / ".gitmodules")
    no_symlink(root / "serveur")
    no_symlink(root / "serveur/components")
    clean(git, root, superproject=True)
    parent = text(git.run(root, "rev-parse", "--verify", "HEAD"))
    require(bool(HEX40.fullmatch(parent)), "FULL_SUPERPROJECT_COMMIT_REQUIRED")
    entries = parse_tree(git.run(root, "ls-tree", "-r", "-z", "--full-tree", parent))
    links = {path: oid for path, (mode, kind, oid) in entries.items() if (mode, kind) == ("160000", "commit")}
    require(set(links) == set(URLS), "GITLINK_SET_MISMATCH")
    modules = entries.get(".gitmodules")
    require(modules is not None and modules[0:2] == ("100644", "blob"), "COMMITTED_GITMODULES_REQUIRED")
    raw = git.run(root, "show", parent + ":.gitmodules")
    require(object_id("blob", raw) == modules[2], "GITMODULES_BLOB_MISMATCH")
    require((root / ".gitmodules").read_bytes() == raw, "GITMODULES_WORKTREE_MISMATCH")
    parse_modules(raw)
    components = tuple(component_state(git, root, path, URLS[path], links[path]) for path in sorted(URLS))
    require(text(git.run(root, "rev-parse", "--verify", "HEAD")) == parent, "SUPERPROJECT_CHANGED")
    clean(git, root, superproject=True)
    return Plan(parent, modules[2], components)


def fetch_arguments(component: Component) -> tuple[str, ...]:
    require(URLS.get(component.path) == component.url and bool(HEX40.fullmatch(component.commit)), "INVALID_FETCH_PLAN")
    return ("fetch", "--depth=1", "--no-tags", "--no-recurse-submodules", "--no-write-fetch-head", component.url, component.commit)


def apply_plan(root: Path, plan: Plan, git: Git | None = None) -> list[dict[str, str]]:
    git = git or Git()
    require(make_plan(root, git) == plan, "PLAN_CHANGED")
    result: list[dict[str, str]] = []
    for component in plan.components:
        # Recheck the committed source of truth and current target before mutations.
        fresh = make_plan(root, git)
        require(fresh.superproject_commit == plan.superproject_commit and fresh.modules_blob == plan.modules_blob, "SUPERPROJECT_CHANGED")
        current = next(item for item in fresh.components if item.path == component.path)
        require(current == component, "COMPONENT_CHANGED")
        target = root / component.path
        if component.action == "verify-only":
            result.append({"path":component.path, "commit":component.commit, "tree":component.tree or "", "action":"verified-existing"})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        no_symlink(target)
        if component.action == "initialize-fetch-checkout":
            target.mkdir(exist_ok=True)
            require(not any(target.iterdir()), "COMPONENT_CHANGED")
            # Empty template disables inherited init hooks; no remote branch is read.
            git.run(target, "init", "--quiet", "--template=", "--initial-branch=bootstrap-unused")
            git.run(target, "config", "--local", "remote.origin.url", component.url)
        else:
            require(component.action == "fetch-checkout-initialized-empty"
                    and all(entry.name == ".git" for entry in target.iterdir()), "COMPONENT_CHANGED")
        git.run(target, *fetch_arguments(component))
        tree = verify_commit_tree(git, target, component.commit)
        require(text(git.run(root, "rev-parse", "--verify", "HEAD")) == plan.superproject_commit, "SUPERPROJECT_CHANGED")
        clean(git, root, superproject=True)
        validate_repository(git, target)
        verify_remote(git, target, component.url)
        # No worktree files may appear while the fetch is in progress.
        require(all(entry.name == ".git" for entry in target.iterdir()), "COMPONENT_CHANGED")
        git.run(target, "-c", "core.logallrefupdates=false", "checkout", "--quiet", "--no-overwrite-ignore", "--detach", component.commit)
        verified = component_state(git, root, component.path, component.url, component.commit)
        require(verified.tree == tree and verified.action == "verify-only", "POST_CHECKOUT_MISMATCH")
        result.append({"path":component.path, "commit":component.commit, "tree":tree, "action":"fetched-pinned-commit"})
    final = make_plan(root, git)
    require(final.superproject_commit == plan.superproject_commit and all(item.action == "verify-only" for item in final.components), "FINAL_PLAN_MISMATCH")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="read-only plan (default)")
    mode.add_argument("--apply", action="store_true", help="fetch only the two pinned commits")
    args = parser.parse_args()
    root = Path(__file__).absolute().parent.parent.parent
    try:
        plan = make_plan(root)
        payload: dict[str, object] = {"status":"planned", "development_only":True, "release_authorized":False, "plan":asdict(plan)}
        if args.apply:
            payload.update(status="prepared", components=apply_plan(root, plan))
        print(json.dumps(payload, sort_keys=True))
        return 0
    except (Refused, OSError, ValueError) as error:
        code = str(error) if isinstance(error, Refused) else "INVALID_OR_UNAVAILABLE_INPUT"
        print(json.dumps({"status":"refused", "code":code, "release_authorized":False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
