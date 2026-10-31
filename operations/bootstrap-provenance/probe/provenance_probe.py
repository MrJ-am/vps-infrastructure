#!/usr/bin/env python3
"""Fixed nonprivileged provenance query; no caller-selected path or command.

Only two documented nixos-version flags and the current-system link are used.
The output is filtered again before leaving the transient sandbox.
"""
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT))
from bounded import Refused, run
from adoption_probe import STORE, safe_readlink, constrain

VERSION = "/run/current-system/sw/bin/nixos-version"
ENVIRONMENT = {"LANG": "C", "LC_ALL": "C", "PATH": "/no-path"}
REVISION = re.compile(rb"[0-9a-f]{40}\n?")
PROGRAM = re.compile(r"/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._?=\-]{1,211}/bin/nixos-version")


def revision(program, flag):
    # The caller is collect() below. No argument or environment can choose flag.
    try:
        raw = run([program, flag], environment=ENVIRONMENT, seconds=2, limit=64)
    except (Refused, OSError):
        return {"state": "unknown", "code": "UNAVAILABLE", "value": None}
    if REVISION.fullmatch(raw) is None:
        return {"state": "unknown", "code": "INVALID_OUTPUT", "value": None}
    return {"state": "observed", "code": "OK", "value": raw.decode("ascii").rstrip("\n")}


def collect():
    before = safe_readlink("/run/current-system")
    match = STORE.fullmatch(before)
    if match is None:
        raise Refused()
    # Resolve only this root-controlled public executable; never return its
    # suffix, contents, interpreter path, diagnostic or any environment value.
    program = Path(VERSION).resolve(strict=True)
    value = program.lstat()
    if (PROGRAM.fullmatch(str(program)) is None or not stat.S_ISREG(value.st_mode)
            or value.st_uid != 0 or value.st_gid != 0 or value.st_mode & 0o022
            or not value.st_mode & 0o111):
        raise Refused()
    configuration = revision(str(program), "--configuration-revision")
    nixpkgs = revision(str(program), "--revision")
    if safe_readlink("/run/current-system") != before:
        raise Refused()
    return {
        "schema_version": 1,
        "operation": "mrjam-system-provenance-v1",
        "authority": "unverified_observation",
        "generation_store_hash": match.group(1),
        "configuration_revision": configuration,
        "nixpkgs_revision": nixpkgs,
        "state_version": None,
    }


def main():
    try:
        if len(sys.argv) != 1 or os.getuid() == 0 or os.geteuid() == 0:
            raise Refused()
        constrain()
        report = collect()
        sys.stdout.write(json.dumps(report, separators=(",", ":"), sort_keys=True) + "\n")
        return 0
    except Exception:
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
