#!/usr/bin/env python3
"""Run the unchanged module assertions in separate local Nix evaluations.

No activation, build or production access. Run apart from memory-heavy VM tests.
All component names come from the selected versioned matrix. ViSe is an explicit
optional qualification and is excluded from the first-deployment matrix.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

SOURCE = Path(__file__).with_name("component.nix")


def check(nixpkgs, destination, include_vise=False):
    if not nixpkgs.is_dir() or destination.exists() or destination.is_symlink():
        raise ValueError("NEW_OUTPUT_AND_NIXPKGS_DIRECTORY_REQUIRED")
    repository = SOURCE.parents[2]
    source_hashes = {
        path.relative_to(repository).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((repository / "operations").rglob("*"))
        if path.is_file() and path.suffix in (".nix", ".py", ".json")
        and "__pycache__" not in path.parts
    }
    command = ["nix-instantiate", "--eval", "--strict", "--json", str(SOURCE),
               "--arg", "nixpkgs", str(nixpkgs.resolve()),
               "--arg", "includeVise", "true" if include_vise else "false"]
    discovery = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=60, check=True)
    names = json.loads(discovery.stdout)
    if (type(names) is not list or not 1 <= len(names) <= 64
            or len(names) != len(set(names))
            or not all(type(name) is str and name.isascii() and name.isidentifier() for name in names)):
        raise ValueError("COMPONENT_LIST_REFUSED")
    destination.mkdir(parents=True)
    results = {}
    for name in names:
        start = time.monotonic()
        with (destination / (name + ".json")).open("xb") as output, (destination / (name + ".log")).open("xb") as errors:
            execution = subprocess.run([*command, "--argstr", "component", name],
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=errors, timeout=300)
        result = {"accepted": False, "checks": None}
        if execution.returncode == 0:
            result = json.loads((destination / (name + ".json")).read_bytes())
        results[name] = {**result, "exit_code": execution.returncode,
                         "wall_seconds": round(time.monotonic() - start, 3)}
        print(json.dumps({"component": name, "accepted": result["accepted"],
                          "exit_code": execution.returncode}), flush=True)
    receipt = {
        "schema_version": 1, "nixpkgs_source": str(nixpkgs.resolve()),
        "source_files_sha256": source_hashes,
        "components": results, "components_executed": len(results),
        "assertions_passed": sum(sum(v is True for v in (r["checks"] or {}).values()) for r in results.values()),
        "overall_compatible": all(r["accepted"] and r["exit_code"] == 0 for r in results.values()),
        "production_ready": False, "production_access": False,
        "optional_vise_included": include_vise,
        "excluded_optional_components": [] if include_vise else ["vise", "postgresqlComposition"],
        "scope": "Sequential synthetic module evaluation; no generation built or activated",
    }
    (destination / "result.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt["overall_compatible"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nixpkgs", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--include-vise", action="store_true",
                        help="Also qualify optional ViSe; never required for the first deployment")
    args = parser.parse_args()
    raise SystemExit(0 if check(args.nixpkgs, args.destination, args.include_vise) else 1)
