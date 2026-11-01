{
  description = "MRJ.am declarative preparation and synthetic qualification for first commissioning";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/6f06d204d8f2d8761d9da78778745974a3216381";
  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      inventoryFixture = nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [ self.nixosModules.inventory ./operations/tests/inventory-fixture.nix ];
      };
      rustEvaluation = import ./operations/tests/module-evaluation.nix { inherit nixpkgs; };
      inventoryEvaluation = import ./operations/tests/inventory-evaluation.nix { inherit nixpkgs; };
      vpsPreparationEvaluation = import ./operations/tests/vps-preparation-evaluation.nix { inherit nixpkgs; };
      vpsMachineEvaluation = import ./operations/tests/vps-machine-evaluation.nix { inherit nixpkgs; };
      viseEvaluation = import ./operations/tests/vise-evaluation.nix { inherit nixpkgs; };
      nextcloudGuardsEvaluation = import ./operations/tests/nextcloud-guards-evaluation.nix { inherit nixpkgs; };
      postgresqlAccessEvaluation = import ./operations/tests/postgresql-access-evaluation.nix { inherit nixpkgs; };
      postgresqlCompositionEvaluation = import ./operations/tests/postgresql-composition-evaluation.nix { inherit nixpkgs; };
      systemProvenanceEvaluation = import ./operations/tests/system-provenance-evaluation.nix { inherit nixpkgs; };
      forgejoEvaluation = import ./operations/forgejo/tests/module-evaluation.nix { inherit nixpkgs; };
      forgejoPinnedEvaluation = import ./operations/forgejo/tests/locked-preparation-evaluation.nix { inherit nixpkgs; };
      forgejoHostEvaluation = import ./operations/forgejo/tests/host-module-evaluation.nix { inherit nixpkgs; };
      preservedServicesEvaluation = import ./operations/tests/preserved-services-evaluation.nix { inherit nixpkgs; };
      coreServicesEvaluation = import ./operations/tests/core-services-evaluation.nix { inherit nixpkgs; };
      gatewayEvaluation = import ./operations/tests/gateway-evaluation.nix { inherit nixpkgs; };
      forgejoPolicyEvaluation = import ./operations/forgejo/tests/policy-module-evaluation.nix { inherit nixpkgs; };
      forgejoRunnerEvaluation = import ./operations/forgejo/tests/runner-module-evaluation.nix { inherit nixpkgs; };
      validationWorkerEvaluation = import ./operations/forgejo/tests/worker-module-evaluation.nix { inherit nixpkgs; };
      validationStagingEvaluation = import ./operations/forgejo/tests/staging-module-evaluation.nix { inherit nixpkgs; };
      visionArchiveEvaluation = import ./operations/tests/vision-archive-evaluation.nix { inherit nixpkgs; };
      visionReplayEvaluation = import ./operations/tests/vision-replay-evaluation.nix { inherit nixpkgs; };
      visionCycleEvaluation = import ./operations/tests/vision-cycle-evaluation.nix { inherit nixpkgs; };
      visionClosureEvaluation = import ./operations/tests/vision-closure-evaluation.nix { inherit nixpkgs; };
      visionAdmissionEvaluation = import ./operations/tests/vision-admission-evaluation.nix { inherit nixpkgs; };
      admissionAdoptionEvaluation = import ./operations/tests/admission-adoption-evaluation.nix { inherit nixpkgs; };
    in {
      nixosModules = {
        rust = import ./operations/nixos/mrjam-rust.nix;
        inventory = import ./operations/nixos/mrjam-inventory.nix;
        forgejo = import ./operations/nixos/mrjam-forgejo.nix;
        forgejoHost = import ./operations/nixos/mrjam-forgejo-host.nix;
        kanidmHost = import ./operations/nixos/mrjam-kanidm-host.nix;
        nextcloudHost = import ./operations/nixos/mrjam-nextcloud-host.nix;
        vpsCoreServices = import ./operations/hosts/mrjam-vps/core-services.nix;
        gateway = import ./operations/nixos/mrjam-gateway.nix;
        forgejoPolicy = import ./operations/nixos/mrjam-forgejo-policy.nix;
        forgejoRunner = import ./operations/nixos/mrjam-forgejo-runner.nix;
        validationWorker = import ./operations/nixos/mrjam-validation-worker.nix;
        validationStaging = import ./operations/nixos/mrjam-validation-staging.nix;
        validationCollector = import ./operations/nixos/mrjam-validation-collector.nix;
        postgresqlAccess = import ./operations/nixos/mrjam-postgresql-access.nix;
        postgresqlPolicy = import ./operations/nixos/mrjam-postgresql-policy.nix;
        # Keep the optional module lazy even when flake outputs are inspected.
        vise = { config, lib, pkgs, ... }@args: import ./operations/nixos/mrjam-vise.nix args;
        nextcloudGuards = import ./operations/nixos/mrjam-nextcloud-guards.nix;
        visionArchive = import ./operations/nixos/mrjam-vision-archive.nix;
        visionReplay = import ./operations/nixos/mrjam-vision-replay.nix;
        visionCycle = import ./operations/nixos/mrjam-vision-cycle.nix;
        visionClosure = import ./operations/nixos/mrjam-vision-closure.nix;
        visionAdmission = import ./operations/nixos/mrjam-vision-admission.nix;
        admissionAdoption = import ./operations/nixos/mrjam-admission-adoption.nix;
        vpsPreparation = import ./operations/nixos/vps-preparation.nix;
        systemProvenance = import ./operations/nixos/mrjam-system-provenance.nix;
      };
      # Deliberately no production nixosConfiguration or default deployable image.
      lib.qualification.rust = rustEvaluation;
      lib.qualification.inventory = inventoryEvaluation;
      lib.qualification.vpsPreparation = vpsPreparationEvaluation;
      lib.qualification.vpsMachine = vpsMachineEvaluation;
      lib.optionalQualification.vise = viseEvaluation;
      lib.qualification.nextcloudGuards = nextcloudGuardsEvaluation;
      lib.qualification.postgresqlAccess = postgresqlAccessEvaluation;
      lib.optionalQualification.postgresqlComposition = postgresqlCompositionEvaluation;
      lib.qualification.systemProvenance = systemProvenanceEvaluation;
      lib.qualification.forgejo = forgejoEvaluation;
      lib.qualification.forgejoPinnedToolchain = forgejoPinnedEvaluation;
      lib.qualification.forgejoHost = forgejoHostEvaluation;
      lib.qualification.preservedServices = preservedServicesEvaluation;
      lib.qualification.coreServices = coreServicesEvaluation;
      lib.qualification.gateway = gatewayEvaluation;
      lib.qualification.forgejoPolicy = forgejoPolicyEvaluation;
      lib.qualification.forgejoRunner = forgejoRunnerEvaluation;
      lib.qualification.validationWorker = validationWorkerEvaluation;
      lib.qualification.validationStaging = validationStagingEvaluation;
      lib.qualification.visionArchive = visionArchiveEvaluation;
      lib.qualification.visionReplay = visionReplayEvaluation;
      lib.qualification.visionCycle = visionCycleEvaluation;
      lib.qualification.visionClosure = visionClosureEvaluation;
      lib.qualification.visionAdmission = visionAdmissionEvaluation;
      lib.qualification.admissionAdoption = admissionAdoptionEvaluation;
      lib.qualification.inventorySshConfig = toString inventoryFixture.config.environment.etc."ssh/sshd_config".source;
      lib.qualification.inventoryAssertions = builtins.all
        (entry: entry.assertion) inventoryFixture.config.assertions;
      packages.${system} = {
        inventory-synthetic = inventoryFixture.config.services.mrjamInventory.package;
        inventory-vps-candidate = import ./operations/targets/inventory-candidate.nix { inherit pkgs; };
        observe-adoption = pkgs.callPackage ./operations/bootstrap-observation/package.nix { };
        observe-provenance = pkgs.callPackage ./operations/bootstrap-provenance/package.nix { };
        observe-services = pkgs.callPackage ./operations/bootstrap-services-v2/package.nix { };
        forgejo-schema-check = pkgs.callPackage ./operations/forgejo/schema-check.nix { };
        preserved-nextcloud = (import ./operations/hosts/mrjam-vps/preserved-packages.nix { inherit system; }).nextcloud;
        preserved-php = (import ./operations/hosts/mrjam-vps/preserved-packages.nix { inherit system; }).php;
        preserved-kanidm = (import ./operations/hosts/mrjam-vps/preserved-packages.nix { inherit system; }).kanidm;
        inventory-sshd-config = inventoryFixture.config.environment.etc."ssh/sshd_config".source;
        openssh-qualified = pkgs.openssh;
        forgejo-preparation = import ./operations/forgejo/locked-preparation.nix { inherit system; };
        admission-adoption = pkgs.callPackage ./operations/migrations/admission/package.nix { };
        validation-stage-sources = pkgs.callPackage ./operations/forgejo/staging-package.nix { };
        received-tests-profile = pkgs.buildEnv {
          name = "mrjam-received-synthetic-test-profile";
          paths = [ pkgs.bash pkgs.coreutils pkgs.openssh pkgs.python3 ];
        };
      };
      # Explicit opt-in: a ViSe failure must never block the first deployment.
      lib.optionalChecks.${system}.vise = {
        vise-module = pkgs.runCommand "mrjam-vise-module-evaluation" {
          result = builtins.toJSON viseEvaluation;
        } ''
          mkdir -p "$out"
          printf '%s\n' "$result" > "$out/result.json"
        '';
        postgresql-composition-module = pkgs.runCommand "mrjam-postgresql-composition-evaluation" {
          result = builtins.toJSON postgresqlCompositionEvaluation;
        } ''
          mkdir -p "$out"
          printf '%s\n' "$result" > "$out/result.json"
        '';
        vise-postgresql-runtime = import ./operations/runtime/vise-postgresql-systemd.nix { inherit nixpkgs; };
      };
      checks.${system} = {
      core-services-module = pkgs.runCommand "mrjam-core-services-evaluation" {
        result = builtins.toJSON coreServicesEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      core-services-runtime = import ./operations/runtime/core-services-systemd.nix { inherit nixpkgs; };
      vps-machine-module = pkgs.runCommand "mrjam-vps-received-machine-evaluation" {
        result = builtins.toJSON vpsMachineEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      nextcloud-guards-module = pkgs.runCommand "mrjam-nextcloud-guards-evaluation" {
        result = builtins.toJSON nextcloudGuardsEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      forgejo-postgresql-runtime = import ./operations/runtime/forgejo-postgresql-systemd.nix { inherit nixpkgs; };
      kanidm-runtime = import ./operations/runtime/kanidm-systemd.nix { inherit nixpkgs; };
      nextcloud-runtime = import ./operations/runtime/nextcloud-systemd.nix { inherit nixpkgs; };
      services-observer-runtime = import ./operations/bootstrap-services-v2/systemd-test.nix { inherit nixpkgs; };
      forgejo-host-module = pkgs.runCommand "mrjam-forgejo-host-evaluation" {
        result = builtins.toJSON forgejoHostEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      preserved-services-module = pkgs.runCommand "mrjam-preserved-services-evaluation" {
        result = builtins.toJSON preservedServicesEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      system-provenance-module = pkgs.runCommand "mrjam-system-provenance-module-evaluation" {
        result = builtins.toJSON systemProvenanceEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      system-provenance-render = import ./operations/tests/system-provenance-build.nix { inherit nixpkgs; };
      rust-module = pkgs.runCommand "mrjam-rust-module-evaluation" {
        result = builtins.toJSON rustEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      inventory-module = pkgs.runCommand "mrjam-inventory-module-evaluation" {
        result = builtins.toJSON inventoryEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      vps-preparation-module = pkgs.runCommand "mrjam-vps-preparation-module-evaluation" {
        result = builtins.toJSON vpsPreparationEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      forgejo-module = pkgs.runCommand "mrjam-forgejo-module-evaluation" {
        result = builtins.toJSON forgejoEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      gateway-module = pkgs.runCommand "mrjam-gateway-module-evaluation" {
        result = builtins.toJSON gatewayEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      forgejo-render = pkgs.callPackage ./operations/forgejo/tests/render-contract.nix { };
      vision-replay-module = pkgs.runCommand "mrjam-vision-replay-module-evaluation" {
        result = builtins.toJSON visionReplayEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      vision-cycle-module = pkgs.runCommand "mrjam-vision-cycle-module-evaluation" {
        result = builtins.toJSON visionCycleEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      vision-closure-module = pkgs.runCommand "mrjam-vision-closure-module-evaluation" {
        result = builtins.toJSON visionClosureEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      vision-admission-module = pkgs.runCommand "mrjam-vision-admission-module-evaluation" {
        result = builtins.toJSON visionAdmissionEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      admission-adoption-module = pkgs.runCommand "mrjam-admission-adoption-module-evaluation" {
        result = builtins.toJSON admissionAdoptionEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      };
    };
}
