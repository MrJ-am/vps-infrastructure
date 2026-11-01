{ nixpkgs ? import ./nixpkgs-vps-observed.nix }:
let
  lock = builtins.fromJSON (builtins.readFile ./nixpkgs-vps-observed.lock.json);
  lib = import (nixpkgs + "/lib");
  inspect = checks:
    let result = builtins.tryEval (builtins.deepSeq checks checks);
    in { accepted = result.success; checks = if result.success then result.value else null; };
  components = {
    inventory = inspect (import ../tests/inventory-evaluation.nix { inherit nixpkgs; });
    vpsPreparation = inspect (import ../tests/vps-preparation-evaluation.nix { inherit nixpkgs; });
    systemProvenance = inspect (import ../tests/system-provenance-evaluation.nix { inherit nixpkgs; revision = lock.input.rev; });
    rust = inspect (import ../tests/module-evaluation.nix { inherit nixpkgs; });
    gateway = inspect (import ../tests/gateway-evaluation.nix { inherit nixpkgs; });
    forgejoGate = inspect (import ../forgejo/tests/module-evaluation.nix { inherit nixpkgs; });
    forgejoPinnedToolchain = inspect (import ../forgejo/tests/locked-preparation-evaluation.nix { inherit nixpkgs; });
  };
in {
  inherit components;
  scope = "Module evaluation against the observed nixpkgs input; not a complete host";
  overall_compatible = lib.all (value: value.accepted) (builtins.attrValues components);
  failed_components = lib.attrNames (lib.filterAttrs (_: value: !value.accepted) components);
  production_ready = false;
}
