# Declared build metadata, not an approval or an authenticated observation.
# The source manifest covers code inputs, never this generation's output/NAR:
# including the latter would introduce a content-hash cycle.
{ config, lib, ... }:
let
  cfg = config.mrjam.systemProvenance;
  hex = size: value: value != null && !builtins.hasContext value
    && builtins.match "[0-9a-f]{${toString size}}" value != null
    && value != lib.concatStrings (lib.replicate size "0");
  requirements = {
    sourceRevision = hex 40 cfg.sourceRevision;
    sourceManifest = hex 64 cfg.sourceManifestSha256;
    nixpkgsRevision = hex 40 cfg.lockedNixpkgsRevision
      && cfg.lockedNixpkgsRevision == config.system.nixos.revision
      && !builtins.hasContext config.system.nixos.revision;
    stateVersion = cfg.expectedStateVersion != null
      && cfg.expectedStateVersion == config.system.stateVersion
      && !builtins.hasContext cfg.expectedStateVersion && !builtins.hasContext config.system.stateVersion;
    configuration = cfg.configurationName != null && !builtins.hasContext cfg.configurationName;
    target = cfg.target != null && !builtins.hasContext cfg.target;
  };
  valid = builtins.all (value: value) (builtins.attrValues requirements);
  record = assert lib.assertMsg valid "mrjamSystemProvenance requires complete, matching build inputs and unchanged stateVersion."; {
    schema_version = 1;
    operation = "mrjam-declared-build-v1";
    authority = "declared_build_metadata";
    source_repository = "MrJ-am/vps-infrastructure";
    source_revision = cfg.sourceRevision;
    source_manifest_sha256 = cfg.sourceManifestSha256;
    nixpkgs_revision = cfg.lockedNixpkgsRevision;
    configuration_name = cfg.configurationName;
    target = cfg.target;
    state_version = config.system.stateVersion;
  };
in {
  options.mrjam.systemProvenance = {
    enable = lib.mkEnableOption "closed metadata for an explicitly selected system build";
    sourceRevision = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Full clean source commit supplied by the source assembly; never a branch or dirty revision.";
    };
    sourceManifestSha256 = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "SHA-256 of the reviewed code-input manifest, excluding system output identities and secrets.";
    };
    lockedNixpkgsRevision = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Full locked input commit; must match the NixOS build's own declared revision.";
    };
    expectedStateVersion = lib.mkOption {
      type = lib.types.nullOr (lib.types.strMatching "[0-9]{2}\\.(05|11)");
      default = null;
      description = "Separately established compatibility value. This module checks it and never sets stateVersion.";
    };
    configurationName = lib.mkOption {
      type = lib.types.nullOr (lib.types.strMatching "[a-z][a-z0-9-]{0,63}");
      default = null;
      description = "Reviewed NixOS configuration name, without paths, addresses or arbitrary text.";
    };
    target = lib.mkOption {
      type = lib.types.nullOr (lib.types.enum [ "mrjam-vps" "synthetic-vps" ]);
      default = null;
      description = "Closed target identifier; a declaration does not authenticate a machine.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = lib.mapAttrsToList (name: assertion: {
      inherit assertion;
      message = "mrjamSystemProvenance: missing or inconsistent ${name}.";
    }) requirements;
    # A conflicting host definition remains a merge error, not an override.
    system.configurationRevision = cfg.sourceRevision;
    environment.etc."mrjam/system-provenance.json" = {
      text = builtins.toJSON record + "\n";
      mode = "0444";
      user = "root";
      group = "root";
    };
  };
}
