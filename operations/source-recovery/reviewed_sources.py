#!/usr/bin/env python3
"""Pack already reviewed local code. No SSH, source evaluation or extraction.

This checks integrity, not confidentiality or the truth of a review declaration.
The private pre-review directory must never be passed to this program or an agent.
"""
import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile

MAX_FILE = 1024 * 1024
MAX_TOTAL = 4 * 1024 * 1024
MAX_MANIFEST = 64 * 1024
MAX_ARCHIVE = 6 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}")


class Refused(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys), "INVALID_FIELDS")


def relative(name):
    require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,179}", name)
            and str(PurePosixPath(name)) == name
            and len(PurePosixPath(name).parts) <= 12
            and all(not part.startswith(".") for part in PurePosixPath(name).parts), "INVALID_PATH")
    return name


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def manifest(raw):
    require(len(raw) <= MAX_MANIFEST, "MANIFEST_LIMIT")
    try:
        value = json.loads(raw, object_pairs_hook=no_duplicates)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise Refused("INVALID_JSON") from None
    exact(value, ("schema_version", "operation", "authority", "target", "entrypoint",
                  "declared_state_version", "declared_graph_complete", "generation_binding", "files"))
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "INVALID_VERSION")
    require(value["operation"] == "mrjam-reviewed-configuration-sources-v1"
            and value["authority"] == "human-reviewed-code-only-declaration"
            and value["target"] == "mrjam-vps" and value["generation_binding"] == "unverified",
            "INVALID_SCOPE")
    require(type(value["declared_graph_complete"]) is bool, "INVALID_GRAPH_DECLARATION")
    files = value["files"]
    # Manifest bytes bound the file list; there is no independent count ceiling.
    require(type(files) is list and len(files) > 0, "FILE_COUNT_LIMIT")
    names, total = set(), 0
    for item in files:
        exact(item, ("path", "bytes", "sha256", "change"))
        name = relative(item["path"])
        require(name != "review.json" and name not in names, "DUPLICATE_OR_RESERVED_PATH")
        names.add(name)
        require(type(item["bytes"]) is int and 0 <= item["bytes"] <= MAX_FILE, "FILE_SIZE_LIMIT")
        require(type(item["sha256"]) is str and HEX.fullmatch(item["sha256"]), "INVALID_DIGEST")
        require(item["change"] in ("unchanged", "redacted", "unknown"), "INVALID_CHANGE_DECLARATION")
        total += item["bytes"]
    require(total <= MAX_TOTAL, "TOTAL_SIZE_LIMIT")
    require(relative(value["entrypoint"]) in names, "ENTRYPOINT_MISSING")
    directories = {str(parent) for name in names for parent in PurePosixPath(name).parents
                   if str(parent) != "."}
    require(not names.intersection(directories) and "review.json" not in directories, "PATH_COLLISION")
    state = value["declared_state_version"]
    exact(state, ("value", "source"))
    if state["value"] is None:
        require(state["source"] is None, "INVALID_STATE_VERSION_DECLARATION")
    else:
        require(type(state["value"]) is str and re.fullmatch(r"[0-9]{2}\.(0[1-9]|1[0-2])", state["value"])
                and type(state["source"]) is str and state["source"] in names,
                "INVALID_STATE_VERSION_DECLARATION")
    return value, names, directories


@contextmanager
def directory(path):
    # Refuse links in every component, including the root supplied by the caller.
    absolute = Path(os.path.abspath(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            new_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new_fd
        yield fd
    finally:
        os.close(fd)


def read_at(root, name, limit):
    fd = os.dup(root)
    try:
        parts = PurePosixPath(name).parts
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(file_fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "REGULAR_SINGLE_LINK_REQUIRED")
            require(before.st_size <= limit, "FILE_SIZE_LIMIT")
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            require(len(raw) == before.st_size and signature(before) == signature(after), "SOURCE_CHANGED")
            return raw
    finally:
        os.close(fd)


def only_manifested(root, names, directories):
    allowed = names | {"review.json"}
    seen = set()

    def visit(fd, prefix):
        # Names of unexpected entries may be checked, never their contents.
        with os.scandir(fd) as entries:
            for entry in entries:
                name = prefix + entry.name
                require(name in allowed or name in directories, "UNDECLARED_ENTRY")
                info = entry.stat(follow_symlinks=False)
                if name in directories:
                    require(stat.S_ISDIR(info.st_mode), "DIRECTORY_REQUIRED")
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        visit(child, name + "/")
                    finally:
                        os.close(child)
                else:
                    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "REGULAR_SINGLE_LINK_REQUIRED")
                    seen.add(name)
    visit(root, "")
    require(seen == allowed, "DECLARED_FILE_MISSING")


def check_bytes(value, payloads):
    for item in value["files"]:
        raw = payloads["source/" + item["path"]]
        require(len(raw) == item["bytes"] and sha(raw) == item["sha256"], "CONTENT_MISMATCH")


def sums(payloads):
    return "".join(sha(raw) + "  " + name + "\n" for name, raw in sorted(payloads.items())).encode("ascii")


def archive_bytes(payloads):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, raw in sorted(payloads.items()):
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode, entry.mtime = len(raw), 0o644, 0
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = ""
            archive.addfile(entry, io.BytesIO(raw))
    raw = stream.getvalue()
    require(len(raw) <= MAX_ARCHIVE, "ARCHIVE_LIMIT")
    return raw


def pack(reviewed_directory, output):
    with directory(reviewed_directory) as root:
        review = read_at(root, "review.json", MAX_MANIFEST)
        value, names, directories = manifest(review)
        only_manifested(root, names, directories)
        payloads = {"review.json": review}
        for item in sorted(value["files"], key=lambda item: item["path"]):
            content = read_at(root, item["path"], MAX_FILE)
            require(len(content) == item["bytes"] and sha(content) == item["sha256"], "CONTENT_MISMATCH")
            payloads["source/" + item["path"]] = content
        payloads["SHA256SUMS"] = sums(payloads)
        raw = archive_bytes(payloads)
    # No partial artifact on a validation failure; never overwrite an existing file.
    output_fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(output_fd, "wb") as destination:
        destination.write(raw)
    return summary(value, raw)


def summary(value, raw):
    return {"operation": "mrjam-reviewed-configuration-sources-v1", "status": "integrity-checked",
            "sha256": sha(raw), "bytes": len(raw), "files": len(value["files"]),
            "confidentiality_verified_by_tool": False, "source_graph_verified_by_tool": False,
            "installed_generation_verified": False, "production_ready": False}


def verify(archive_path, expected):
    require(type(expected) is str and HEX.fullmatch(expected), "INVALID_DIGEST")
    path = Path(archive_path)
    with directory(path.absolute().parent) as parent:
        raw = read_at(parent, path.name, MAX_ARCHIVE)
    require(sha(raw) == expected, "ARCHIVE_DIGEST_MISMATCH")
    payloads = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for entry in archive:
                # MAX_ARCHIVE already bounds the input, including member headers.
                require(entry.name not in payloads, "ARCHIVE_MEMBER_COUNT")
                require(entry.isfile() and entry.type == tarfile.REGTYPE and not entry.pax_headers
                        and entry.uid == 0 and entry.gid == 0 and entry.mode == 0o644
                        and entry.mtime == 0 and entry.uname == "" and entry.gname == ""
                        and 0 <= entry.size <= MAX_FILE, "INVALID_ARCHIVE_MEMBER")
                require(entry.name in ("review.json", "SHA256SUMS") or
                        (entry.name.startswith("source/") and relative(entry.name[7:])), "INVALID_ARCHIVE_PATH")
                stream = archive.extractfile(entry)
                require(stream is not None, "INVALID_ARCHIVE_MEMBER")
                with stream:
                    payloads[entry.name] = stream.read(MAX_FILE + 1)
                require(len(payloads[entry.name]) == entry.size, "TRUNCATED_ARCHIVE_MEMBER")
    except (tarfile.TarError, UnicodeError, OverflowError):
        raise Refused("INVALID_ARCHIVE") from None
    require("review.json" in payloads and "SHA256SUMS" in payloads, "REQUIRED_MEMBER_MISSING")
    value, names, _ = manifest(payloads["review.json"])
    require(set(payloads) == {"review.json", "SHA256SUMS"} | {"source/" + name for name in names},
            "UNDECLARED_ARCHIVE_MEMBER")
    check_bytes(value, payloads)
    require(payloads["SHA256SUMS"] == sums({k: v for k, v in payloads.items() if k != "SHA256SUMS"}),
            "SUMS_MISMATCH")
    require(raw == archive_bytes(payloads), "NONCANONICAL_ARCHIVE")
    return summary(value, raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("pack")
    create.add_argument("reviewed_directory", type=Path)
    create.add_argument("output", type=Path)
    check = sub.add_parser("verify")
    check.add_argument("archive", type=Path)
    check.add_argument("sha256")
    args = parser.parse_args()
    try:
        result = pack(args.reviewed_directory, args.output) if args.command == "pack" else verify(args.archive, args.sha256)
    except Refused as error:
        print(json.dumps({"status": "refused", "code": str(error)}))
        return 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print(json.dumps({"status": "refused", "code": "INVALID_LOCAL_INPUT"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
