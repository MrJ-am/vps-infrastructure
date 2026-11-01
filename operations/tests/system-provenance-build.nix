{ nixpkgs, revision ? "6f06d204d8f2d8761d9da78778745974a3216381" }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  source = "1111111111111111111111111111111111111111";
  digest = pkgs.lib.concatStrings (pkgs.lib.replicate 64 "2");
  cfg = (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-system-provenance.nix {
      system.stateVersion = "24.11";
      system.nixos.revision = revision;
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
      mrjam.systemProvenance = {
        enable = true;
        sourceRevision = source;
        sourceManifestSha256 = digest;
        lockedNixpkgsRevision = revision;
        expectedStateVersion = "24.11";
        configurationName = "synthetic-vps";
        target = "synthetic-vps";
      };
    } ];
  }).config;
  versionProgram = pkgs.lib.findFirst (p: pkgs.lib.getName p == "nixos-version")
    (throw "nixos-version not present in the synthetic profile") cfg.environment.systemPackages;
in assert builtins.all (a: a.assertion) cfg.assertions;
pkgs.runCommand "mrjam-system-provenance-render-contract" {
  nativeBuildInputs = [ pkgs.python3 ];
  preferLocalBuild = true;
  allowSubstitutes = false;
} ''
  mkdir -p "$out"
  cp ${cfg.environment.etc."mrjam/system-provenance.json".source} "$out/system-provenance.json"
  ${versionProgram}/bin/nixos-version --configuration-revision > "$out/configuration-revision"
  ${versionProgram}/bin/nixos-version --revision > "$out/nixpkgs-revision"
  ${pkgs.python3}/bin/python3 -I -S - "$out" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
metadata = json.loads((root / "system-provenance.json").read_bytes())
assert (root / "configuration-revision").read_text() == "${source}\n"
assert (root / "nixpkgs-revision").read_text() == "${revision}\n"
assert metadata == {
  "schema_version": 1, "operation": "mrjam-declared-build-v1",
  "authority": "declared_build_metadata", "source_repository": "MrJ-am/vps-infrastructure",
  "source_revision": "${source}", "source_manifest_sha256": "${digest}",
  "nixpkgs_revision": "${revision}", "configuration_name": "synthetic-vps",
  "target": "synthetic-vps", "state_version": "24.11",
}
(root / "checks.json").write_text(json.dumps({
  "rendered_record_matches": True, "actual_nixos_version_matches": True,
  "production_access": False, "production_activation": False,
}, sort_keys=True) + "\n")
PY
''
