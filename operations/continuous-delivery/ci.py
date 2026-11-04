#!/usr/bin/env python3
"""Forgejo CI: fetch exact sources, build and test in the Nix sandbox."""
import fcntl
import hashlib
import http.client
import io
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
    for directory, repository in [("vision", "vision"), ("mateval", "matheval")]:
        item = json.loads(api("repos/" + REPOSITORY + "/contents/serveur/components/"
                              + directory + "?ref=" + revision))
        if item["type"] != "submodule":
            raise ValueError("Expected pinned application component")
        target = destination / "serveur/components" / directory
        if target.exists():
            target.rmdir()
        export(repository, item["sha"], target)


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
            checkout(revision, source)
            # The installed recipe defines the tests; branch code cannot replace it.
            expression = ("import " + str(RECIPES / "server.nix")
                          + " { source = builtins.path { name = \"source\"; path = "
                          + json.dumps(str(source)) + "; }"
                          + "; revision = " + json.dumps(revision) + "; }")
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
            temporary_result.write_text(json.dumps({"revision": revision, "output": output,
                                                     "schema_digest": schema_digest(source / "serveur")}) + "\n")
            os.replace(temporary_result, results / (revision + ".json"))
            print("Tests passed; artifact: " + output, flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never print request headers, credentials or response bodies.
        print("CI failed: " + type(error).__name__, file=sys.stderr)
        sys.exit(1)
