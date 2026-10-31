#!/usr/bin/env python3
"""Propose a fresh exact source lock and materialization for public frontends."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from frontend_inputs import PUBLIC_EXTENSIONS, STYLE, materialize, select_application
from prepare import HERE, Refused, checked_bytes, digest, put, regular_bytes, relative
from select_sources import commit_id

STYLE_PUBLIC = {
    "log": ["assets/mrjam/animations.js"],
    "audition": ["assets/mrjam/animations.js", "assets/mrjam/mathematiques.js", "assets/mrjam/ecriture.css", "assets/mrjam/palette/Palette-Audio.svg"],
}

def git_blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def propose(vision: Path, vision_revision: str, infrastructure: Path, infra_revision: str,
            styles: Path, vision_style: Path, elm_home: Path, resources: Path,
            resource_lock: Path) -> tuple[dict, dict[str, Path]]:
    roots = {"vision": vision, "infrastructure": infrastructure, "vision-style": vision_style,
             "elm-home": elm_home, "resources": resources}
    files = {}
    frontends = {}

    def add(target: str, root: str, path: str, checksum: str, **provenance):
        relative(target)
        relative(path)
        if target in files:
            raise Refused("FRONTEND_DESTINATION_COLLISION")
        checked_bytes(roots[root], path, checksum)
        files[target] = {"root": root, "path": path, "sha256": checksum, **provenance}

    infra_binding = json.loads(regular_bytes(infrastructure, "frontends.lock.json"))
    pins = {e["id"]: e["style"]["revision"] for e in infra_binding["frontends"]}
    if any(pins.get(name) != STYLE[name] for name in ("log", "audition")):
        raise Refused("CONSUMED_STYLE_PIN_MISMATCH")
    for name in ("vision", "log", "audition"):
        root = vision if name == "vision" else infrastructure
        root_name = "vision" if name == "vision" else "infrastructure"
        revision = vision_revision if name == "vision" else infra_revision
        selected = select_application(root, commit_id(revision), name)
        for path, specification in selected.items():
            local = path if name == "vision" else path.removeprefix(f"interface-{name}/")
            add(f"applications/{name}/{local}", root_name, path, specification["sha256"], git_blob=specification["git_blob"])
        frontends[name] = {"source_commit": revision, "style_revision": STYLE[name],
                           "repository": "MrJ-am/vision" if name == "vision" else "MrJ-am/vps-infrastructure"}
        if name != "vision":
            frontends[name]["style_public_files"] = STYLE_PUBLIC[name]
            frontends[name]["signature_revision"] = "17194087eec9162bb5372221c43e1de0501dfe6a"

    vision_binding = json.loads(checked_bytes(vision, "interface/style.lock.json", files["applications/vision/interface/style.lock.json"]["sha256"]))
    if vision_binding["revision"] != STYLE["vision"]:
        raise Refused("CONSUMED_STYLE_PIN_MISMATCH")
    frontends["vision"]["signature_revision"] = commit_id(vision_binding["signature"])
    for path, checksum in vision_binding["fichiers"].items():
        add(f"styles/{STYLE['vision']}/{path}", "vision-style", path, checksum)

    for revision in (STYLE["log"], STYLE["audition"]):
        root_name = "style-" + revision
        roots[root_name] = styles / revision
        tree = json.loads(regular_bytes(roots[root_name], "tree.json"))
        if tree["truncated"] is not False:
            raise Refused("TRUNCATED_STYLE_TREE")
        count = 0
        public = {"public/" + p for name, revision_for_name in STYLE.items() if revision_for_name == revision for p in STYLE_PUBLIC.get(name, [])}
        for entry in tree["tree"]:
            path = entry["path"]
            selected = path.startswith("src/") and path.endswith(".elm") or path in public
            if not selected:
                continue
            if entry["type"] != "blob" or entry["mode"] != "100644" or entry["size"] > 1024 * 1024:
                raise Refused("STYLE_FILE_TYPE_REFUSED")
            data = regular_bytes(roots[root_name], path, 1024 * 1024)
            if git_blob_id(data) != entry["sha"]:
                raise Refused("STYLE_GIT_BLOB_MISMATCH")
            add(f"styles/{revision}/{path}", root_name, path, digest(data), git_blob=entry["sha"])
            if path.startswith("src/"):
                count += 1
        if count != 54:
            raise Refused("STYLE_SOURCE_SET_MISMATCH")

    elm_lock = json.loads(regular_bytes(HERE, "elm-dependencies.lock.json"))
    add("elm-home/0.19.1/packages/registry.dat", "elm-home", "0.19.1/packages/registry.dat", elm_lock["registry_sha256"])
    versions = {name: p["version"] for name, p in elm_lock["packages"].items()}
    for name in ("vision", "log", "audition"):
        key = f"applications/{name}/" + ("interface/" if name == "vision" else "") + "elm.json"
        specification = files[key]
        manifest = json.loads(checked_bytes(roots[specification["root"]], specification["path"], specification["sha256"]))
        for section in ("dependencies", "test-dependencies"):
            for group in ("direct", "indirect"):
                if any(versions.get(package) != version for package, version in manifest[section][group].items()):
                    raise Refused("ELM_PACKAGE_VERSION_MISMATCH")
    for package, specification in elm_lock["packages"].items():
        for filename, checksum in specification["files"].items():
            path = f"0.19.1/packages/{package}/{specification['version']}/{filename}"
            add("elm-home/" + path, "elm-home", path, checksum)

    # These non-code resources keep their separately reviewed source provenance.
    # An absent or changed font/vendor pin cannot be replaced by a convenient file.
    resource_bytes = regular_bytes(resource_lock.parent, resource_lock.name)
    extras = json.loads(resource_bytes)
    if extras["schema_version"] != 1:
        raise Refused("RESOURCE_LOCK_VERSION")
    for resource in extras["files"]:
        name = resource["frontend"]
        if name not in ("log", "audition"):
            raise Refused("RESOURCE_FRONTEND_REFUSED")
        destination = resource["destination"]
        if not destination.startswith(("assets/mrjam/", "vendor/katex/")) or Path(destination).suffix not in PUBLIC_EXTENSIONS:
            raise Refused("RESOURCE_PATH_REFUSED")
        if f"styles/{STYLE[name]}/public/{destination}" in files:
            raise Refused("RESOURCE_STYLE_OVERWRITE_REFUSED")
        add(f"resources/{name}/{destination}", "resources", resource["source_path"], resource["sha256"], provenance=resource["provenance"])
    return ({"schema_version": 1, "status": "proposed-source-selection-not-validation-authority", "frontends": frontends,
             "resource_lock_sha256": digest(resource_bytes), "elm_dependency_lock_sha256": digest(regular_bytes(HERE, "elm-dependencies.lock.json")), "files": files}, roots)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("vision", "infrastructure", "styles", "vision-style", "elm-home", "resources", "resource-lock", "source-lock", "destination"):
        parser.add_argument("--" + flag, required=True, type=Path)
    parser.add_argument("--vision-commit", required=True)
    parser.add_argument("--infrastructure-commit", required=True)
    args = parser.parse_args()
    try:
        lock, roots = propose(args.vision, args.vision_commit, args.infrastructure, args.infrastructure_commit,
                              args.styles, args.vision_style, args.elm_home, args.resources, args.resource_lock)
        put(args.source_lock.parent, args.source_lock.name, (json.dumps(lock, sort_keys=True, indent=2) + "\n").encode())
        result = materialize(args.source_lock, roots, args.destination)
        result["source_lock_sha256"] = digest(args.source_lock.read_bytes())
        result["materialization_sha256"] = digest((args.destination / "materialization.json").read_bytes())
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps({"status": "refused", "code": str(error) if isinstance(error, Refused) else "FRONTEND_SOURCE_SELECTION_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
