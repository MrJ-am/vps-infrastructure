{ nixpkgs, revision ? "6f06d204d8f2d8761d9da78778745974a3216381" }:
let
  lib = import (nixpkgs + "/lib");
  source = "1111111111111111111111111111111111111111";
  digest = lib.concatStrings (lib.replicate 64 "2");
  context = builtins.getContext (builtins.toFile "synthetic-provenance-context" "synthetic only");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-system-provenance.nix {
      # Entirely synthetic compatibility value, never inferred for the VPS.
      system.stateVersion = "24.11";
      system.nixos.revision = revision;
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
    } extra ];
  }).config;
  settings = {
    enable = true;
    sourceRevision = source;
    sourceManifestSha256 = digest;
    lockedNixpkgsRevision = revision;
    expectedStateVersion = "24.11";
    configurationName = "synthetic-vps";
    target = "synthetic-vps";
  };
  disabled = evaluate { };
  enabled = evaluate { mrjam.systemProvenance = settings; };
  entry = enabled.environment.etc."mrjam/system-provenance.json";
  document = builtins.fromJSON entry.text;
  fails = change: !(builtins.tryEval (builtins.deepSeq
    (evaluate { mrjam.systemProvenance = settings // change; }).environment.etc."mrjam/system-provenance.json".text
    true)).success;
  conflict = evaluate {
    mrjam.systemProvenance = settings;
    system.configurationRevision = "3333333333333333333333333333333333333333";
  };
  results = {
    disabledCreatesNoRecord = !(disabled.environment.etc ? "mrjam/system-provenance.json");
    disabledDoesNotSetRevision = disabled.system.configurationRevision == null;
    recordsFullSourceCommit = document.source_revision == source && enabled.system.configurationRevision == source;
    recordsInputManifestOnly = document.source_manifest_sha256 == digest && !(document ? generation) && !(document ? nar_hash);
    recordsMatchingNixpkgs = document.nixpkgs_revision == revision;
    preservesStateVersion = enabled.system.stateVersion == "24.11" && document.state_version == "24.11";
    recordHasClosedFields = builtins.attrNames document == [ "authority" "configuration_name" "nixpkgs_revision" "operation"
      "schema_version" "source_manifest_sha256" "source_repository" "source_revision" "state_version" "target" ];
    declarationIsNotApproval = document.authority == "declared_build_metadata" && !(document ? production_authorized);
    recordIsRootOwnedReadOnly = entry.user == "root" && entry.group == "root" && entry.mode == "0444";
    noUnitsAdded = builtins.attrNames enabled.systemd.services == builtins.attrNames disabled.systemd.services;
    noAccountsAdded = builtins.attrNames enabled.users.users == builtins.attrNames disabled.users.users;
    noRevisionFallback = fails { sourceRevision = null; };
    rejectsBranch = fails { sourceRevision = "main"; };
    rejectsDirtyRevision = fails { sourceRevision = source + "-dirty"; };
    rejectsUppercaseRevision = fails { sourceRevision = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"; };
    rejectsZeroRevision = fails { sourceRevision = lib.concatStrings (lib.replicate 40 "0"); };
    requiresManifestHash = fails { sourceManifestSha256 = null; };
    rejectsMalformedManifest = fails { sourceManifestSha256 = "sha256-arbitrary"; };
    rejectsZeroManifest = fails { sourceManifestSha256 = lib.concatStrings (lib.replicate 64 "0"); };
    requiresNixpkgsRevision = fails { lockedNixpkgsRevision = null; };
    rejectsNixpkgsMismatch = fails { lockedNixpkgsRevision = source; };
    requiresStateVersionEvidence = fails { expectedStateVersion = null; };
    rejectsStateVersionChange = fails { expectedStateVersion = "26.05"; };
    requiresConfigurationName = fails { configurationName = null; };
    requiresTarget = fails { target = null; };
    rejectsRevisionDependencyContext = fails { sourceRevision = builtins.appendContext source context; };
    rejectsManifestDependencyContext = fails { sourceManifestSha256 = builtins.appendContext digest context; };
    rejectsNixpkgsDependencyContext = fails { lockedNixpkgsRevision = builtins.appendContext revision context; };
    rejectsStateVersionDependencyContext = fails { expectedStateVersion = builtins.appendContext "24.11" context; };
    rejectsConfigurationDependencyContext = fails { configurationName = builtins.appendContext "synthetic-vps" context; };
    rejectsTargetDependencyContext = fails { target = builtins.appendContext "synthetic-vps" context; };
    hostRevisionConflictRefused = !(builtins.tryEval (builtins.deepSeq conflict.system.configurationRevision true)).success;
    assertionsPass = builtins.all (item: item.assertion) enabled.assertions;
  };
in assert builtins.all (value: value) (builtins.attrValues results); results
