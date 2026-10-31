#!/usr/bin/env python3
"""Copy pinned verifier outputs without rebuilding or patching the executable.

This local packaging step authenticates no reviewer, policy or deployment right.
Only public compiled code and the closed verifier content receipt are accepted.
"""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile

LIMITS = {"server": 64 * 1024**2, "frontend.tar": 64 * 1024**2, "verification.json": 64 * 1024}
FRONTENDS = {"audition", "log", "logique", "mateval", "style", "style-logo", "vision"}
SHA = re.compile(r"[0-9a-f]{64}")


class Refused(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys), "DOCUMENT_FIELDS_REFUSED")


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "DUPLICATE_FIELD")
            result[key] = value
        return result

    def invalid(_):
        raise Refused("JSON_NUMBER_REFUSED")

    return json.loads(raw, object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid)


def read_file(path, limit):
    """Open every ancestor without following links; refuse special files first."""
    path = Path(path).absolute()
    require(".." not in path.parts, "PATH_REFUSED")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
        with os.fdopen(child, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit, "INPUT_FILE_REFUSED")
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            stable = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            require(len(data) == before.st_size and stable(before) == stable(after), "INPUT_CHANGED")
            return data
    finally:
        os.close(fd)


def checked_inputs(source, lock_raw):
    lock = parse(lock_raw)
    exact(lock, ("schema_version", "kind", "proposal_sha256", "rules_revision", "policy_sha256", "files"))
    require(type(lock["schema_version"]) is int and lock["schema_version"] == 1
            and lock["kind"] == "mrjam-qualified-artifact-import", "LOCK_VERSION_REFUSED")
    for key in ("proposal_sha256", "policy_sha256"):
        require(type(lock[key]) is str and SHA.fullmatch(lock[key]), "LOCK_HASH_REFUSED")
    require(type(lock["rules_revision"]) is str and re.fullmatch(r"[0-9a-f]{40}", lock["rules_revision"]), "RULES_REFUSED")
    exact(lock["files"], LIMITS)
    files = {}
    for name, limit in LIMITS.items():
        pin = lock["files"][name]
        exact(pin, ("bytes", "sha256"))
        require(type(pin["bytes"]) is int and 0 < pin["bytes"] <= limit
                and type(pin["sha256"]) is str and SHA.fullmatch(pin["sha256"]), "FILE_PIN_REFUSED")
        data = read_file(Path(source) / name, limit)
        require(len(data) == pin["bytes"] and sha(data) == pin["sha256"], "ARTIFACT_HASH_MISMATCH")
        files[name] = data
    # This is an architecture guard, not execution or qualification of this ELF.
    server = files["server"]
    require(len(server) >= 64 and server[:7] == b"\x7fELF\x02\x01\x01"
            and int.from_bytes(server[18:20], "little") == 62, "SERVER_FORMAT_REFUSED")
    receipt = parse(files["verification.json"])
    exact(receipt, ("schema_version", "decision", "authority", "independent_adoption_established",
                    "production_authorized", "proposal_sha256", "rules_revision", "policy_sha256",
                    "steps", "sources", "artifacts", "not_established"))
    require(type(receipt["schema_version"]) is int and receipt["schema_version"] == 1
            and receipt["decision"] == "passed" and receipt["authority"] == "local-verifier-content-receipt"
            and receipt["independent_adoption_established"] is False
            and receipt["production_authorized"] is False, "RECEIPT_SCOPE_REFUSED")
    require(all(receipt[key] == lock[key] for key in ("proposal_sha256", "rules_revision", "policy_sha256")), "RECEIPT_BINDING_REFUSED")
    require(receipt["artifacts"] == [{"name": name, **lock["files"][name]} for name in ("server", "frontend.tar")], "RECEIPT_ARTIFACTS_REFUSED")
    require(type(receipt["steps"]) is list and 0 < len(receipt["steps"]) <= 128, "CHECKS_REFUSED")
    steps = []
    for step in receipt["steps"]:
        require(type(step) is dict and type(step.get("name")) is str and step.get("status") == "passed", "CHECKS_REFUSED")
        steps.append(step["name"])
    minimum = {"complete-trees-submodules-and-locked-tools", "rust-format", "rust-clippy-all-features",
               "rust-http-postgres-rls-tls-tests", "rust-release", "independent-http-release-bytes", "elm-rules-208"}
    minimum |= {prefix + name for name in FRONTENDS for prefix in ("elm-compile-", "elm-review-prepare-", "elm-review-", "frontend-resource-closure-")}
    require(len(steps) == len(set(steps)) and minimum <= set(steps), "INCOMPLETE_QUALIFICATION_RECEIPT")
    return files


def frontend_files(raw):
    """Read bounded USTAR bytes; never use extract/extractall on input members."""
    result = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive:
            name = member.name
            path = PurePosixPath(name)
            require(member.type == tarfile.REGTYPE and not member.pax_headers
                    and 1 < len(path.parts) and path.parts[0] in FRONTENDS
                    and re.fullmatch(r"[A-Za-z0-9._+@/-]{1,300}", name)
                    and str(path) == name and not path.is_absolute()
                    and not any(part in (".", "..") for part in path.parts)
                    and name not in result and len(result) < 4096
                    and 0 <= member.size <= 16 * 1024**2
                    and member.mode == 0o444 and member.uid == member.gid == member.mtime == 0,
                    "FRONTEND_MEMBER_REFUSED")
            total += member.size
            require(total <= LIMITS["frontend.tar"], "FRONTEND_SIZE_LIMIT")
            stream = archive.extractfile(member)
            require(stream is not None, "FRONTEND_MEMBER_REFUSED")
            data = stream.read(member.size + 1)
            require(len(data) == member.size, "FRONTEND_TRUNCATED")
            result[name] = data
    require({PurePosixPath(name).parts[0] for name in result} == FRONTENDS, "FRONTEND_SCOPE_REFUSED")
    require(not any(str(parent) in result for name in result for parent in PurePosixPath(name).parents),
            "FRONTEND_FILE_DIRECTORY_COLLISION")
    return result


def install(source, lock_path, expected_lock, destination):
    require(type(expected_lock) is str and SHA.fullmatch(expected_lock), "LOCK_HASH_REFUSED")
    lock_raw = read_file(lock_path, 16 * 1024)
    require(sha(lock_raw) == expected_lock, "LOCK_HASH_MISMATCH")
    files = checked_inputs(source, lock_raw)
    frontends = frontend_files(files["frontend.tar"])
    destination = Path(destination)
    # The Nix builder owns a fresh private destination. Never adopt an existing
    # tree, follow an ancestor symlink or leave a partially checked package.
    require(not destination.exists() and not destination.is_symlink(), "NEW_OUTPUT_REQUIRED")
    for ancestor in destination.absolute().parents:
        require(not ancestor.is_symlink(), "OUTPUT_SYMLINK_REFUSED")
    destination.mkdir(mode=0o755)

    def put(name, data, mode):
        target = destination / name
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
        target.chmod(mode)
        require(sha(read_file(target, max(len(data), 1))) == sha(data), "OUTPUT_HASH_MISMATCH")

    put("bin/mrjam-server", files["server"], 0o555)
    # The existing runtime configuration binder pins artifact.json. Use the
    # unchanged verifier receipt, which already binds this exact server hash.
    put("artifact.json", files["verification.json"], 0o444)
    for name in ("frontend.tar", "verification.json"):
        put("share/mrjam/" + name, files[name], 0o444)
    put("share/mrjam/import.lock.json", lock_raw, 0o444)
    for name, data in frontends.items():
        # Empty public assets are allowed; their bytes are still pinned by tar.
        if data:
            put("share/mrjam/frontends/" + name, data, 0o444)
        else:
            target = destination / "share/mrjam/frontends" / name
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            target.touch(mode=0o444, exist_ok=False)
    return {"status": "copied-without-rebuild", "frontend_files": len(frontends), "lock_sha256": expected_lock,
            "independent_adoption_established": False, "production_authorized": False}


def main():
    require(len(sys.argv) == 5, "ARGUMENTS_REFUSED")
    print(json.dumps(install(*sys.argv[1:]), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (Refused, OSError, ValueError, TypeError, KeyError, tarfile.TarError):
        # No payload, path, or traceback is reflected at this boundary.
        print('{"status":"refused","production_authorized":false}')
        raise SystemExit(2) from None
