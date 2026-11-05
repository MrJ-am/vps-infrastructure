#!/usr/bin/env python3
"""Forgejo CI: fetch exact sources, build and test in the Nix sandbox."""
import fcntl
import hashlib
import http.client
import io
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

REPOSITORY = "MrJ-am/vps-infrastructure"
STATE = Path(os.environ.get("MRJAM_CI_STATE", "/var/lib/mrjam-ci"))
RECIPES = Path(__file__).resolve().parent


def api(path, timeout=120):
    token = Path(os.environ["CREDENTIALS_DIRECTORY"], "source-token").read_text().strip()
    connection = http.client.HTTPConnection("127.0.0.1", 3004, timeout=timeout)
    try:
        connection.request("GET", "/api/v1/" + path,
                           headers={"Authorization": "token " + token, "Host": "forge.mrj.am"})
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError("Forgejo source request HTTP " + str(response.status))
        return response.read(128 * 1024 * 1024)
    finally:
        connection.close()


def export(repository, revision, destination):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected an exact Git commit")
    raw = api("repos/MrJ-am/" + repository + "/archive/" + revision + ".tar.gz")
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        members = archive.getmembers()
        prefix = members[0].name.split("/")[0] + "/"
        for member in members:
            if member.name.rstrip("/") == prefix.rstrip("/"):
                continue
            if not member.name.startswith(prefix):
                raise ValueError("Unexpected archive root")
            member.name = member.name[len(prefix):]
            archive.extract(member, destination, filter="data")


def checkout(revision, destination):
    export("vps-infrastructure", revision, destination)
    components = {}
    for directory, repository in [("vision", "vision"), ("mateval", "matheval")]:
        item = json.loads(api("repos/" + REPOSITORY + "/contents/serveur/components/"
                              + directory + "?ref=" + revision))
        if item["type"] != "submodule":
            raise ValueError("Expected pinned application component")
        target = destination / "serveur/components" / directory
        if target.exists():
            target.rmdir()
        export(repository, item["sha"], target)
        components[directory] = item["sha"]
    return components


def schema_digest(workspace):
    """A binary-only release never runs or changes a SQL migration."""
    files = {}
    for path in sorted(workspace.rglob("*.sql")):
        if any(part in ("migrations", "reference-schemas") for part in path.parts):
            files[str(path.relative_to(workspace))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def main():
    if len(sys.argv) != 3 or sys.argv[1] != REPOSITORY:
        raise ValueError("This CI installation serves vps-infrastructure")
    revision = sys.argv[2]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected an exact Git commit")
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "build.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix="source-", dir=STATE) as temporary:
            source = Path(temporary) / "source"
            components = checkout(revision, source)
            recipes = source / "operations/continuous-delivery"
            complete = (recipes / "release.nix").is_file()
            if complete:
                pins = json.loads((recipes / "components/pins.json").read_text())
                for name, commit in components.items():
                    if pins["applications"][name][1] != commit:
                        raise ValueError("Frontend and server component revisions differ: " + name)
                spec = importlib.util.spec_from_file_location("component_preparation", recipes / "components/prepare.py")
                helper = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(helper)
                helper.prepare(source, STATE / "dependency-cache", export)
            recipe = "release.nix" if complete else "server.nix"
            previous = None
            deployed = Path("/var/lib/mrjam-delivery/current.json")
            if complete and deployed.is_file():
                state = json.loads(deployed.read_text())
                previous = state["output"]
                if state.get("format") == 2:
                    previous = json.loads(Path(previous, "release.json").read_text())["server"]
            # Recipes follow the exact tested Git revision, including the full
            # system and delivery engine; no separately installed recipe pin.
            expression = ("let source = builtins.path { name = \"source\"; path = "
                          + json.dumps(str(source)) + "; }; in import (source + "
                          + json.dumps("/operations/continuous-delivery/" + recipe)
                          + ") { inherit source; revision = " + json.dumps(revision) + "; "
                          + ("previousServer = " + json.dumps(previous) + "; " if previous else "") + "}")
            result = subprocess.run(["nix-build", "--no-out-link", "--cores", "2",
                                     "--max-jobs", "1", "--expr", expression],
                                    check=True, stdout=subprocess.PIPE, text=True)
            output = result.stdout.strip().splitlines()[-1]
            if Path(output, "share/mrjam/source-revision").read_text().strip() != revision:
                raise ValueError("Build revision mismatch")
            results = STATE / "results"
            results.mkdir(exist_ok=True)
            roots = STATE / "gcroots"
            roots.mkdir(exist_ok=True)
            subprocess.run(["nix-store", "--add-root", str(roots / revision),
                            "--indirect", "--realise", output], check=True, stdout=subprocess.DEVNULL)
            temporary_result = results / (revision + ".tmp")
            metadata = {"revision": revision, "output": output,
                        "schema_digest": schema_digest(source / "serveur")}
            if complete:
                metadata["format"] = 2
                metadata["schema_digests"] = {"server": metadata["schema_digest"],
                    "vise": schema_digest(source / ".delivery-inputs/apps/vise/backend")}
            temporary_result.write_text(json.dumps(metadata) + "\n")
            os.replace(temporary_result, results / (revision + ".json"))
            print("Tests passed; artifact: " + output, flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never print request headers, credentials or response bodies.
        print("CI failed: " + type(error).__name__, file=sys.stderr)
        sys.exit(1)
