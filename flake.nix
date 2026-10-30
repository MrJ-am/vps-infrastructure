{
  description = "MRJ.am declarative preparation; deployment freeze, synthetic checks only";
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
      forgejoEvaluation = import ./operations/forgejo/tests/module-evaluation.nix { inherit nixpkgs; };
    in {
      nixosModules = {
        rust = import ./operations/nixos/mrjam-rust.nix;
        inventory = import ./operations/nixos/mrjam-inventory.nix;
        forgejo = import ./operations/nixos/mrjam-forgejo.nix;
        vpsPreparation = import ./operations/nixos/vps-preparation.nix;
      };
      # Deliberately no production nixosConfiguration or default deployable image.
      lib.qualification.rust = rustEvaluation;
      lib.qualification.inventory = inventoryEvaluation;
      lib.qualification.forgejo = forgejoEvaluation;
      lib.qualification.inventorySshConfig = toString inventoryFixture.config.environment.etc."ssh/sshd_config".source;
      lib.qualification.inventoryAssertions = builtins.all
        (entry: entry.assertion) inventoryFixture.config.assertions;
      packages.${system} = {
        inventory-synthetic = inventoryFixture.config.services.mrjamInventory.package;
        inventory-sshd-config = inventoryFixture.config.environment.etc."ssh/sshd_config".source;
        openssh-qualified = pkgs.openssh;
        forgejo-preparation = pkgs.callPackage ./operations/forgejo/package.nix { };
        received-tests-profile = pkgs.buildEnv {
          name = "mrjam-received-synthetic-test-profile";
          paths = [ pkgs.bash pkgs.coreutils pkgs.openssh pkgs.python3 ];
        };
      };
      checks.${system} = {
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
      forgejo-module = pkgs.runCommand "mrjam-forgejo-module-evaluation" {
        result = builtins.toJSON forgejoEvaluation;
      } ''
        mkdir -p "$out"
        printf '%s\n' "$result" > "$out/result.json"
      '';
      forgejo-render = pkgs.callPackage ./operations/forgejo/tests/render-contract.nix { };
      };
    };
}
