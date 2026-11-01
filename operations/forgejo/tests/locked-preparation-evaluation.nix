{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  lock = builtins.fromJSON (builtins.readFile ../../../flake.lock);
  candidateSource = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${lock.nodes.nixpkgs.locked.rev}.tar.gz";
    sha256 = lock.nodes.nixpkgs.locked.narHash;
  };
  candidatePkgs = import candidateSource { system = "x86_64-linux"; config = { }; overlays = [ ]; };
  hostPkgs = import nixpkgs { system = "x86_64-linux"; };
  evaluate = modules: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ {
      system.stateVersion = "24.11"; # Synthetic fixture, not an installed value.
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
    } ] ++ modules;
  }).config;
  plainHost = evaluate [ ];
  base = evaluate [ ../../nixos/mrjam-forgejo.nix ];
  poisoned = evaluate [ ../../nixos/mrjam-forgejo.nix {
    nixpkgs.overlays = [ (_: _: {
      forgejo = throw "HOST_FORGEJO_MUST_NOT_BE_USED";
      forgejo-runner = throw "HOST_RUNNER_MUST_NOT_BE_USED";
      pandoc = throw "HOST_RENDERER_MUST_NOT_BE_USED";
    }) ];
  } ];
  original = candidatePkgs.callPackage ../package.nix { };
  pinned = import ../locked-preparation.nix { };
  rejects = value: !(builtins.tryEval (builtins.deepSeq value true)).success;
  results = {
    moduleKeepsExactCandidateDerivation = base.services.mrjamForgejo.preparation.drvPath == original.drvPath;
    moduleKeepsExactCandidateOutput = toString base.services.mrjamForgejo.preparation == toString original;
    helperKeepsExactCandidate = pinned.drvPath == original.drvPath;
    hostOverridesCannotSubstituteTools = poisoned.services.mrjamForgejo.preparation.drvPath == original.drvPath;
    hostNixpkgsIsPreserved = base.system.nixos.revision == plainHost.system.nixos.revision
      && base.system.nixos.version == plainHost.system.nixos.version;
    # Upstream NixOS defaults to forgejo-lts, not pkgs.forgejo. Compare with
    # the actual unmodified host module instead of guessing its default.
    hostPackageIsPreserved = base.services.forgejo.package.drvPath == plainHost.services.forgejo.package.drvPath;
    stateVersionIsPreserved = base.system.stateVersion == "24.11";
    noForgejoService = !base.services.forgejo.enable && !(base.systemd.services ? forgejo);
    noNewSystemPackage = !(builtins.elem (toString pinned) (map toString base.environment.systemPackages));
    unsupportedPlatformRejected = rejects ((import ../locked-preparation.nix { system = "aarch64-linux"; }).drvPath);
    changedForgejoVersionRejected = rejects ((candidatePkgs.callPackage ../package.nix {
      forgejo = candidatePkgs.forgejo // { version = "0.0.0"; };
    }).drvPath);
    changedRunnerVersionRejected = rejects ((candidatePkgs.callPackage ../package.nix {
      forgejo-runner = candidatePkgs.forgejo-runner // { version = "0.0.0"; };
    }).drvPath);
    changedRendererVersionRejected = rejects ((candidatePkgs.callPackage ../package.nix {
      pandoc = candidatePkgs.pandoc // { version = "0.0.0"; };
    }).drvPath);
    hostSubstitutionStillRejectedIfVersionsDiffer = hostPkgs.forgejo.version == "17.0.1" ||
      rejects ((hostPkgs.callPackage ../package.nix { }).drvPath);
  };
in assert builtins.all (value: value) (builtins.attrValues results); results
