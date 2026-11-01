#!/usr/bin/env python3
"""Prove first-deployment evaluation survives broken optional ViSe inputs.

Only temporary copies and Nix evaluation are used. No build or VPS access.
Pass an already verified local nixpkgs source and a new output directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

REPOSITORY = Path(__file__).resolve().parents[2]
OPTIONAL_CHECKS = ["postgresql-composition-module", "vise-module", "vise-postgresql-runtime"]
MARKER = "OPTIONAL_VISE_INTENTIONALLY_UNAVAILABLE"


def nix_path(path):
    return "(builtins.toPath " + json.dumps(str(path.resolve())).replace("${", r"\${") + ")"


def check(nixpkgs, destination):
    if not nixpkgs.is_dir() or destination.exists() or destination.is_symlink():
        raise ValueError("NEW_OUTPUT_AND_NIXPKGS_DIRECTORY_REQUIRED")
    destination.mkdir(parents=True)
    results = {}
    np = nix_path(nixpkgs)

    def evaluate(name, expression, expected_failure=False):
        command = ["nix-instantiate", "--eval", "--strict", "--json", "--expr", expression]
        execution = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=300)
        (destination / (name + ".json")).write_bytes(execution.stdout)
        (destination / (name + ".log")).write_bytes(execution.stderr)
        accepted = (execution.returncode != 0 and MARKER.encode() in execution.stderr
                    if expected_failure else execution.returncode == 0)
        value = None if execution.returncode else json.loads(execution.stdout)
        if not expected_failure:
            accepted = accepted and isinstance(value, dict) and bool(value) and all(v is True for v in value.values())
        results[name] = {"accepted": accepted, "exit_code": execution.returncode,
                         "expected_failure": expected_failure, "checks": value,
                         "expression": expression,
                         "stderr_sha256": hashlib.sha256(execution.stderr).hexdigest()}
        print(json.dumps({"case": name, "accepted": accepted}), flush=True)

    def host(root):
        return f'import ({nix_path(root)} + "/operations/tests/vps-machine-evaluation.nix") {{ nixpkgs = {np}; }}'

    evaluate("original-host", host(REPOSITORY))
    evaluate("optional-profile-retained", f"""
      let cfg = (import ({np} + "/nixos/lib/eval-config.nix") {{
        system = "x86_64-linux";
        modules = [ ({nix_path(REPOSITORY)} + "/operations/hosts/mrjam-vps/configuration-with-vise.nix") ];
      }}).config;
      in {{
        optionalModuleAvailable = cfg.services ? mrjamVise;
        stillDisabled = !cfg.services.mrjamVise.enable;
        observedIdentityRetained = cfg.services.mrjamVise.adoption.uid == 981
          && cfg.services.mrjamVise.adoption.gid == 981;
        noArtifactInvented = cfg.services.mrjamVise.artifactRoot == null;
        noServiceCreated = !(cfg.systemd.services ? vise);
        stateVersionPreserved = cfg.system.stateVersion == "26.05";
      }}
    """)
    with tempfile.TemporaryDirectory(prefix="mrjam-optional-vise-") as directory:
        fixture = Path(directory)
        shutil.copytree(REPOSITORY / "operations", fixture / "operations",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(REPOSITORY / "flake.nix", fixture / "flake.nix")
        # Poison optional inputs; accidental use must fail, not pass silently.
        for name in ("nixos/mrjam-vise.nix", "tests/vise-evaluation.nix",
                     "tests/postgresql-composition-evaluation.nix",
                     "runtime/vise-postgresql-systemd.nix", "vise/package.nix"):
            (fixture / "operations" / name).write_text(f'throw "{MARKER}"\n')
        (fixture / "operations/received/20261101/vps-reviewed-sources/extracted/source"
         / "etc/nixos/vise-hosting/module.nix").unlink()
        report_path = fixture / "operations/received/20261101/services-v1.json"
        report = json.loads(report_path.read_bytes())
        report["accounts"]["etp_carnet"] = {"state": "unknown", "uid": None, "gid": None}
        report["services"]["vise"]["state"] = "unknown"
        report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
        target_path = fixture / "operations/targets/mrjam-vps.json"
        target = json.loads(target_path.read_bytes())
        target["services_observation"]["report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
        target_path.write_text(json.dumps(target) + "\n")
        evaluate("host-with-broken-vise-and-unknown-identity", host(fixture))

        # Use the real pinned flake library; no network or flake input resolution.
        prefix = f"""
          let source = {np};
              pin = {{ outPath = source; }} // (import (source + "/flake.nix")).outputs {{ self = pin; }};
              outputs = (import ({nix_path(fixture)} + "/flake.nix")).outputs {{ self = outputs; nixpkgs = pin; }};
              matrix = import ({nix_path(fixture)} + "/operations/compatibility/evaluation.nix") {{ nixpkgs = source; }};
              extended = import ({nix_path(fixture)} + "/operations/compatibility/evaluation.nix") {{ nixpkgs = source; includeVise = true; }};
              optionalNames = builtins.fromJSON {json.dumps(json.dumps(OPTIONAL_CHECKS))};
          in
        """
        evaluate("default-selection-with-broken-vise", prefix + """{
          noOptionalFlakeChecks = builtins.all (name: !(builtins.hasAttr name outputs.checks.x86_64-linux)) optionalNames;
          optionalChecksRetained = builtins.attrNames outputs.lib.optionalChecks.x86_64-linux.vise == optionalNames;
          optionalModuleIsLazy = builtins.isFunction outputs.nixosModules.vise;
          coreDerivationStillEvaluates = builtins.isString outputs.checks.x86_64-linux.vps-machine-module.drvPath;
          noOptionalDefaultQualification = !(outputs.lib.qualification ? vise) && !(outputs.lib.qualification ? postgresqlComposition);
          defaultMatrixExcludesVise = !(matrix.components ? vise) && !(matrix.components ? postgresqlComposition)
            && !matrix.optional_vise_included && matrix.excluded_optional_components == [ "vise" "postgresqlComposition" ];
          optInMatrixRetainsVise = extended.components ? vise && extended.components ? postgresqlComposition
            && extended.optional_vise_included && extended.excluded_optional_components == [ ];
        }""")
        for name in OPTIONAL_CHECKS:
            evaluate("optional-failure-" + name, prefix + f'outputs.lib.optionalChecks.x86_64-linux.vise."{name}".drvPath',
                     expected_failure=True)

    receipt = {"schema_version": 1, "nixpkgs_source": str(nixpkgs.resolve()),
               "cases": results, "all_passed": all(r["accepted"] for r in results.values()),
               "production_access": False, "generation_built_or_activated": False}
    (destination / "result.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt["all_passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nixpkgs", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if check(args.nixpkgs, args.destination) else 1)
