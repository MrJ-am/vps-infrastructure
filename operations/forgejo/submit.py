#!/usr/bin/env python3
"""Dedicated collector service: submit one digest and retain code artifacts.

Only the fixed local worker socket is contacted. No candidate stdout, path,
command, host URL or credential is accepted. The resulting receipt is unsigned;
adopting a separate validation/signing authority remains a deployment condition.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import socket
import stat
import struct
import sys
import time

SOCKET = "/run/mrjam-validation/request.sock"
POLICY = "/etc/mrjam-validation-submit/policy.json"
ARTIFACT_ROOT = "/var/lib/mrjam-validation-collector/artifacts"
ARTIFACTS = (("server", 64 * 1024 * 1024), ("frontend.tar", 64 * 1024 * 1024), ("verification.json", 65536))
HEX = re.compile(r"[0-9a-f]{64}")


class Refused(Exception):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "DUPLICATE_KEY")
        result[key] = value
    return result


def parse(raw):
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(Refused("INVALID_NUMBER")))
    except Refused:
        raise
    except Exception:
        raise Refused("INVALID_JSON") from None


def validate_receipt(value, proposal, rules):
    require(type(value) is dict and set(value) == {"schema_version", "decision", "proposal_sha256", "rules_revision", "artifacts", "authority"}, "INVALID_RECEIPT")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1 and value["decision"] == "passed", "VALIDATION_FAILED")
    require(value["authority"] == "local-controller-receipt" and value["proposal_sha256"] == proposal and value["rules_revision"] == rules, "IDENTITY_MISMATCH")
    require(type(value["artifacts"]) is list and len(value["artifacts"]) == len(ARTIFACTS), "INVALID_ARTIFACTS")
    for entry, (name, limit) in zip(value["artifacts"], ARTIFACTS):
        require(type(entry) is dict and set(entry) == {"name", "bytes", "sha256"}, "INVALID_ARTIFACTS")
        require(entry["name"] == name and type(entry["bytes"]) is int and 0 < entry["bytes"] <= limit and type(entry["sha256"]) is str and HEX.fullmatch(entry["sha256"]), "INVALID_ARTIFACTS")
    return value


def receive(connection, directory, proposal, rules, *, deadline):
    def read(maximum):
        remaining = deadline - time.monotonic()
        require(remaining > 0, "COLLECTION_TIMEOUT")
        connection.settimeout(remaining)
        return connection.recv(maximum)
    header = bytearray()
    while True:
        byte = read(1)
        require(byte, "TRUNCATED_RECEIPT")
        if byte == b"\n":
            break
        header.extend(byte)
        require(len(header) <= 4096, "RECEIPT_LIMIT")
    receipt = validate_receipt(parse(bytes(header)), proposal, rules)
    for artifact in receipt["artifacts"]:
        fd = os.open(artifact["name"], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=directory)
        try:
            remaining = artifact["bytes"]
            hashed = hashlib.sha256()
            while remaining:
                block = read(min(65536, remaining))
                require(block, "TRUNCATED_ARTIFACT")
                require(os.write(fd, block) == len(block), "ARTIFACT_STORAGE_FAILED")
                hashed.update(block)
                remaining -= len(block)
            require(hashed.hexdigest() == artifact["sha256"], "ARTIFACT_HASH_MISMATCH")
            os.fsync(fd)
        finally:
            os.close(fd)
    require(read(1) == b"", "EXTRA_ARTIFACT_DATA")
    fd = os.open("receipt.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=directory)
    try:
        encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
        require(os.write(fd, encoded) == len(encoded), "ARTIFACT_STORAGE_FAILED")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory)
    return receipt


def cached(root, proposal, rules):
    directory = os.open(proposal, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
    try:
        info = os.fstat(directory)
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, "UNSAFE_CACHE")
        require(set(os.listdir(directory)) == {"receipt.json", *(name for name, _ in ARTIFACTS)}, "UNSAFE_CACHE")
        def open_file(name):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                meta = os.fstat(fd)
                require(stat.S_ISREG(meta.st_mode) and meta.st_uid == os.getuid() and meta.st_nlink == 1 and stat.S_IMODE(meta.st_mode) == 0o400, "UNSAFE_CACHE")
                return fd
            except Exception:
                os.close(fd)
                raise
        fd = open_file("receipt.json")
        with os.fdopen(fd, "rb") as stream:
            require(os.fstat(stream.fileno()).st_size <= 4096, "RECEIPT_LIMIT")
            receipt = validate_receipt(parse(stream.read(4097)), proposal, rules)
        for entry in receipt["artifacts"]:
            fd = open_file(entry["name"])
            with os.fdopen(fd, "rb") as stream:
                require(os.fstat(stream.fileno()).st_size == entry["bytes"], "ARTIFACT_HASH_MISMATCH")
                hashed = hashlib.sha256()
                size = 0
                while block := stream.read(65536):
                    size += len(block)
                    require(size <= entry["bytes"], "ARTIFACT_HASH_MISMATCH")
                    hashed.update(block)
                require(hashed.hexdigest() == entry["sha256"] and size == entry["bytes"], "ARTIFACT_HASH_MISMATCH")
        return receipt
    finally:
        os.close(directory)


def proposal_request(fd):
    deadline = time.monotonic() + 5
    raw = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        require(remaining > 0 and select.select([fd], [], [], remaining)[0], "REQUEST_TIMEOUT")
        block = os.read(fd, 66 - len(raw))
        if not block:
            break
        raw.extend(block)
        require(len(raw) <= 65, "INVALID_PROPOSAL")
    require(re.fullmatch(rb"[0-9a-f]{64}\n", bytes(raw)), "INVALID_PROPOSAL")
    return raw[:-1].decode("ascii")


def main():
    root = lock = staging = None
    staging_name = None
    try:
        require(len(sys.argv) == 1 and os.getuid() != 0, "INVALID_INVOCATION")
        proposal = proposal_request(sys.stdin.fileno())
        fd = os.open(POLICY, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            meta = os.fstat(stream.fileno())
            require(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and not meta.st_mode & 0o222 and meta.st_size <= 4096, "UNSAFE_POLICY")
            value = parse(stream.read(4097))
        require(type(value) is dict and set(value) == {"rules_revision"} and type(value["rules_revision"]) is str and re.fullmatch(r"[0-9a-f]{40}", value["rules_revision"]), "INVALID_POLICY")
        rules = value["rules_revision"]
        root = os.open(ARTIFACT_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        meta = os.fstat(root)
        require(meta.st_uid == os.getuid() and stat.S_IMODE(meta.st_mode) == 0o700, "UNSAFE_CACHE")
        lock = os.open(".collection.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=root)
        meta = os.fstat(lock)
        require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1 and meta.st_uid == os.getuid() and stat.S_IMODE(meta.st_mode) == 0o600, "UNSAFE_CACHE")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        entries = os.listdir(root)
        require(all(name == ".collection.lock" or HEX.fullmatch(name) for name in entries), "INCOMPLETE_PREVIOUS_COLLECTION")
        if proposal in entries:
            receipt = cached(root, proposal, rules)
        else:
            require(len(entries) <= 16, "ARTIFACT_RETENTION_LIMIT")
            staging_name = ".staging-" + proposal
            os.mkdir(staging_name, 0o700, dir_fd=root)
            staging = os.open(staging_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            entry = os.lstat(SOCKET)
            require(stat.S_ISSOCK(entry.st_mode) and entry.st_uid == 0 and stat.S_IMODE(entry.st_mode) == 0o660, "UNTRUSTED_SOCKET")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(5)
                connection.connect(SOCKET)
                _, peer_uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
                require(peer_uid == 0, "UNTRUSTED_SOCKET")
                connection.sendall(proposal.encode("ascii") + b"\n")
                connection.shutdown(socket.SHUT_WR)
                receipt = receive(connection, staging, proposal, rules, deadline=time.monotonic() + 1840)
            os.close(staging)
            staging = None
            os.rename(staging_name, proposal, src_dir_fd=root, dst_dir_fd=root)
            staging_name = None
            os.fsync(root)
        print(json.dumps({**receipt, "collection": "retained-code-artifacts", "authenticated_validation_authority": False}, sort_keys=True, separators=(",", ":")))
        return 0
    except Refused as error:
        print(json.dumps({"decision": "reject", "code": str(error)}, separators=(",", ":")))
        return 2
    except Exception:
        print('{"decision":"reject","code":"COLLECTION_FAILED"}')
        return 2
    finally:
        if staging is not None:
            os.close(staging)
        if root is not None and staging_name is not None:
            try:
                directory = os.open(staging_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
                try:
                    for name in ("receipt.json", *(name for name, _ in ARTIFACTS)):
                        try:
                            os.unlink(name, dir_fd=directory)
                        except FileNotFoundError:
                            pass
                finally:
                    os.close(directory)
                os.rmdir(staging_name, dir_fd=root)
            except OSError:
                pass # Leave an explicit incomplete state; next request refuses.
        if lock is not None:
            os.close(lock)
        if root is not None:
            os.close(root)


if __name__ == "__main__":
    raise SystemExit(main())
