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
      systemProvenanceEvaluation = import ./operations/tests/system-provenance-evaluation.nix { inherit nixpkgs; };
      forgejoEvaluation = import ./operations/forgejo/tests/module-evaluation.nix { inherit nixpkgs; };
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
        gateway = import ./operations/nixos/mrjam-gateway.nix;
        forgejoPolicy = import ./operations/nixos/mrjam-forgejo-policy.nix;
        forgejoRunner = import ./operations/nixos/mrjam-forgejo-runner.nix;
        validationWorker = import ./operations/nixos/mrjam-validation-worker.nix;
        validationStaging = import ./operations/nixos/mrjam-validation-staging.nix;
        validationCollector = import ./operations/nixos/mrjam-validation-collector.nix;
        postgresqlAccess = import ./operations/nixos/mrjam-postgresql-access.nix;
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
      lib.qualification.systemProvenance = systemProvenanceEvaluation;
      lib.qualification.forgejo = forgejoEvaluation;
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
        inventory-sshd-config = inventoryFixture.config.environment.etc."ssh/sshd_config".source;
        openssh-qualified = pkgs.openssh;
        forgejo-preparation = pkgs.callPackage ./operations/forgejo/package.nix { };
        admission-adoption = pkgs.callPackage ./operations/migrations/admission/package.nix { };
        validation-stage-sources = pkgs.callPackage ./operations/forgejo/staging-package.nix { };
        received-tests-profile = pkgs.buildEnv {
          name = "mrjam-received-synthetic-test-profile";
          paths = [ pkgs.bash pkgs.coreutils pkgs.openssh pkgs.python3 ];
        };
      };
      checks.${system} = {
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
