"""Build-time binding of public configuration to immutable output manifests.

This is not a production observation or a release approval. The Rust parser
must validate the same configuration first; no credential or database is read.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

STORE = re.compile(r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+")


def require(condition):
    if not condition:
        raise ValueError("INVALID_CONFIGURATION_BINDING")


def read_public(path, limit):
    require(path.is_absolute() and ".." not in path.parts)
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    descriptor = None
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=directory)
        metadata = os.fstat(descriptor)
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_size <= limit)
        data = bytearray()
        while len(data) <= limit:
            part = os.read(descriptor, min(65536, limit + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        require(len(data) <= limit)
        return bytes(data)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


def unique(items):
    result = {}
    for key, value in items:
        require(key not in result)
        result[key] = value
    return result


def credential_bindings(configuration, slot):
    require(slot in ("blue", "green"))
    names = []
    prefix = f"/run/credentials/mrjam-rust-{slot}.service/"

    def check(value, name):
        if value is not None:
            require(value == prefix + name)
            names.append(name)

    mateval = configuration.get("mateval")
    if mateval is not None:
        check(mateval["database"].get("password_file"), "db-mateval")
        administration = mateval.get("administration_database")
        if administration is not None:
            check(administration.get("password_file"), "db-mateval-admin")
        check(mateval.get("activation_sha256_file"), "mateval-activation-sha256")
    vision = configuration.get("vision")
    if vision is not None:
        check(vision["database"].get("password_file"), "db-vision")
        for field, name in (("deletion_journal", "db-vision-journal"),
                            ("administration_database", "db-vision-admin")):
            if vision.get(field) is not None:
                check(vision[field].get("password_file"), name)
        check(vision.get("admission_approval_credential_file"), "admission-approval")
    if configuration.get("audition") is not None:
        check(configuration["audition"].get("password_file"), "db-audition")
    return sorted(names)


def verify(config_path, slot, server, server_manifest_sha256):
    config_bytes = read_public(config_path, 65536)
    configuration = json.loads(config_bytes, object_pairs_hook=unique)
    require(STORE.fullmatch(server) is not None)
    require(re.fullmatch(r"[0-9a-f]{64}", server_manifest_sha256) is not None)
    server_manifest = read_public(Path(server) / "artifact.json", 2 * 1024 * 1024)
    require(hashlib.sha256(server_manifest).hexdigest() == server_manifest_sha256)
    assets = []
    for asset in configuration["assets"]:
        require(STORE.fullmatch(asset["directory"]) is not None)
        manifest = read_public(Path(asset["directory"]) / "artifact.json", 2 * 1024 * 1024)
        require(hashlib.sha256(manifest).hexdigest() == asset["manifest_sha256"])
        assets.append({key: asset[key] for key in ("host", "directory", "manifest_sha256", "mount")})
    public_ca = None
    if configuration.get("log") is not None:
        log = configuration["log"]
        path = Path(log["ca_file"])
        require(len(path.parts) >= 5 and STORE.fullmatch(str(Path(*path.parts[:4]))) is not None)
        require(".." not in path.parts and str(path) == log["ca_file"])
        require(hashlib.sha256(read_public(path, 256 * 1024)).hexdigest() == log["ca_sha256"])
        public_ca = {"file": log["ca_file"], "sha256": log["ca_sha256"]}
    return {"schema_version": 1, "kind": "public-runtime-configuration", "slot": slot,
            "configuration_sha256": hashlib.sha256(config_bytes).hexdigest(),
            "server_store_path": server, "server_manifest_sha256": server_manifest_sha256,
            "assets": assets, "credential_names": credential_bindings(configuration, slot),
            "public_ca": public_ca, "production_qualification": False}


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 5)
        result = verify(Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4])
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    except Exception:
        sys.stderr.write("INVALID_CONFIGURATION_BINDING\n")
        raise SystemExit(65)
