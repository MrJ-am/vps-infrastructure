{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  target = builtins.fromJSON (builtins.readFile ../targets/mrjam-vps.json);
  reportFile = ../received/20261031/adoption-v2.json;
  report = builtins.fromJSON (builtins.readFile reportFile);
  provenanceFile = ../received/20261101/provenance-v1.json;
  provenance = builtins.fromJSON (builtins.readFile provenanceFile);
  search = target.source_search_observation;
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/vps-preparation.nix {
      # Invented host for evaluation only; never an installed VPS value.
      system.stateVersion = "24.11";
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
    } extra ];
  }).config;
  disabled = evaluate { };
  enabled = evaluate {
    services.mrjamInventory.enable = lib.mkForce true;
    services.openssh.enable = true;
    services.openssh.openFirewall = false;
  };
  package = import ../targets/inventory-candidate.nix { inherit pkgs; };
  # Inspect data only in this evaluation test; the package keeps its dependency
  # context and is separately checked after the actual build.
  runtime = builtins.fromJSON (builtins.unsafeDiscardStringContext package.runtime);
  results = {
    reportBytesBound = builtins.hashFile "sha256" reportFile == target.adoption_observation.report_sha256;
    observationRemainsUnauthenticated = report.authority == "unverified_observation" && target.adoption_observation.authority == report.authority;
    observedIdsArePinned = report.account.uid == 980 && report.account.gid == 980
      && disabled.services.mrjamInventory.adoption.uid == report.account.uid
      && disabled.services.mrjamInventory.adoption.gid == report.account.gid;
    allServicesStayDisabled = !disabled.services.mrjamInventory.enable && !disabled.services.mrjamRust.enable
      && !disabled.services.mrjamForgejo.enable && !disabled.services.mrjamGateway.enable;
    noAccountOrGroupCreated = !(disabled.users.users ? mrjam-inventory) && !(disabled.users.groups ? mrjam-inventory);
    noKeyOrSshServiceCreated = !(disabled.environment.etc ? "ssh/mrjam-inventory-authorized-keys")
      && !disabled.services.openssh.enable;
    noStateVersionInference = target.system_state_version == null && disabled.system.stateVersion == "24.11";
    noSourceOrFullGenerationInvented = target.installed_source_commit == null && target.installed_generation == null
      && !target.adoption_observation.complete_generation_identity;
    noExecutionReadinessInferred = !target.production_execution_ready && !target.inventory_adoption.enable;
    provenanceBytesBound = builtins.hashFile "sha256" provenanceFile == target.provenance_observation.report_sha256;
    provenanceIsOnlyObservation = provenance.authority == "unverified_observation"
      && !target.provenance_observation.complete_generation_identity
      && !target.provenance_observation.continuous_generation_identity_proven;
    missingConfigurationRevisionStaysUnknown = provenance.configuration_revision.state == "unknown"
      && provenance.configuration_revision.value == null && target.installed_source_commit == null;
    observedNixpkgsIsRecordedWithoutSubstitution = target.provenance_observation.nixpkgs_revision == provenance.nixpkgs_revision
      && provenance.nixpkgs_revision.value == "c5c4a43b0e8056328ec4529f735cabdb8f1942bb";
    generationHashComparisonIsExplicit = target.provenance_observation.same_store_hash_as_adoption_v2
      && provenance.generation_store_hash == report.generation.current.store_hash;
    noBuildMetadataInvented = !disabled.mrjam.systemProvenance.enable
      && !(disabled.environment.etc ? "mrjam/system-provenance.json");
    sourceSearchReportsBound = builtins.all (item:
      builtins.hashFile "sha256" (../.. + "/${item.reference}") == item.sha256
      && builtins.stringLength (builtins.readFile (../.. + "/${item.reference}")) == item.bytes
    ) search.report_references;
    sourceSearchIsStillUnauthenticated = search.authority == "unverified_observation"
      && !search.candidate_file_bound_to_running_generation && !search.candidate_file_content_reviewed;
    candidatePathDoesNotInventSource = search.candidate_entrypoint == "/etc/nixos/configuration.nix"
      && search.candidate_file_exists && search.candidate_file_resolves_to_itself
      && !search.git_checkout_at_candidate_directory && search.source_commit == null
      && search.source_repository == null && search.relative_entrypoint == null;
    sourceSearchDoesNotInventCompatibility = search.state_version == null && search.imports == null
      && target.system_state_version == null;
    noCloudAccessFromSpectreReport = !search.cloud_access_authorized;
    fixtureAssertionsPass = builtins.all (entry: entry.assertion) enabled.assertions;
    enabledFixturePreservesIdentity = enabled.users.users.mrjam-inventory.uid == 980
      && enabled.users.groups.mrjam-inventory.gid == 980;
    enabledFixtureRestrictsAccount = enabled.users.users.mrjam-inventory.extraGroups == [ ]
      && enabled.users.users.mrjam-inventory.hashedPassword == "!";
    standalonePackageMatchesModule = package.drvPath == enabled.services.mrjamInventory.package.drvPath;
    packagePinsObservedIdentity = runtime.uid == 980 && runtime.gid == 980;
    packagePinsApprovedPublicKey = runtime.publicKeys == disabled.services.mrjamInventory.publicKeys;
  };
in assert builtins.all (value: value) (builtins.attrValues results); results
