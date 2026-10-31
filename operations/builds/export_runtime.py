#!/usr/bin/env python3
"""Local export of an already built Rust output; never installs or deploys it."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def command(*args):
    return subprocess.check_output(args, timeout=90)


def metadata(path):
    with path.open("rb") as stream:
        return {"sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
                "bytes": path.stat().st_size}


def export(root, destination):
    if not re.fullmatch(r"/nix/store/[0-9a-z]{32}-mrjam-server-preparation-0\.1\.0-[0-9a-f]{12}", root):
        raise ValueError("RUST_OUTPUT_REQUIRED")
    if not destination.is_absolute() or destination.exists() or destination.is_symlink():
        raise ValueError("NEW_ABSOLUTE_DESTINATION_REQUIRED")
    info = json.loads(command("nix", "path-info", "--offline", "--json", "--json-format", "1", "--recursive", root))
    command("nix", "store", "verify", "--offline", "--recursive", "--no-trust", root)
    artifact_bytes = (Path(root) / "artifact.json").read_bytes()
    artifact = json.loads(artifact_bytes)
    if artifact["artifact"] != "rust-server" or set(artifact["payload_sha256"]) != {"bin/mrjam-server"}:
        raise ValueError("RUST_MANIFEST_REQUIRED")
    original = Path(root) / "bin/mrjam-server"
    if metadata(original)["sha256"] != artifact["payload_sha256"]["bin/mrjam-server"]:
        raise ValueError("RUST_CONTENT_MISMATCH")
    glibc = [path for path in info if re.fullmatch(r"/nix/store/[0-9a-z]{32}-glibc-[0-9.]+-[0-9]+", path)]
    libgcc = [path for path in info if re.fullmatch(r"/nix/store/[0-9a-z]{32}-xgcc-[0-9.]+-libgcc", path)]
    if len(glibc) != 1 or len(libgcc) != 1 or info[root]["references"] != glibc:
        raise ValueError("UNQUALIFIED_RUNTIME_DEPENDENCIES")
    destination.mkdir(parents=True)
    (destination / "libraries").mkdir()
    copies = {"mrjam-server": original,
              "libraries/ld-linux-x86-64.so.2": Path(glibc[0]) / "lib/ld-linux-x86-64.so.2",
              "libraries/libc.so.6": Path(glibc[0]) / "lib/libc.so.6",
              "libraries/libm.so.6": Path(glibc[0]) / "lib/libm.so.6",
              "libraries/libgcc_s.so.1": Path(libgcc[0]) / "lib/libgcc_s.so.1"}
    selected = {}
    for relative, source in copies.items():
        resolved = source.resolve(strict=True)
        if not resolved.is_file() or not any(resolved.is_relative_to(path) for path in info):
            raise ValueError("RUNTIME_FILE_OUTSIDE_CLOSURE")
        target = destination / relative
        shutil.copyfile(resolved, target)
        target.chmod(0o555)
        identity = metadata(resolved)
        if metadata(target) != identity:
            raise ValueError("RUNTIME_COPY_CHANGED")
        selected[relative] = {"source": str(source), **identity}
    (destination / "artifact.json").write_bytes(artifact_bytes)
    raw = destination / "mrjam-runtime.nix-export"
    with raw.open("xb") as output:
        subprocess.run(["nix-store", "--export", *sorted(info)], stdout=output, check=True, timeout=90)
    compressed = destination / "mrjam-runtime.nix-export.gz"
    with raw.open("rb") as source, compressed.open("xb") as output, gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as stream:
        shutil.copyfileobj(source, stream)
    receipt = {"schema_version": 1, "authority": "unverified-local-export",
               "scope": "unchanged Nix bytes for local tests; explicit copied ELF loader; not a deployment approval",
               "root": root, "closure": info, "artifact_manifest": metadata(destination / "artifact.json"),
               "copies": selected, "exports": {file.name: metadata(file) for file in (raw, compressed)},
               "recursive_content_verification": True, "production_access": False}
    with (destination / "export.json").open("x") as output:
        json.dump(receipt, output, indent=2, sort_keys=True)
        output.write("\n")
    print(json.dumps({"exported": root, "closure_paths": len(info), "binary_sha256": selected["mrjam-server"]["sha256"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    export(args.root, args.destination)
