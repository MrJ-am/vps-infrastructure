# Composition prepared in the authoritative VPS repository. This is not a host
# definition: no hardware, network, stateVersion, key or current service is guessed.
{ lib, ... }:
let target = builtins.fromJSON (builtins.readFile ../targets/mrjam-vps.json);
in {
  imports = [ ./mrjam-inventory.nix ./mrjam-rust.nix ./mrjam-forgejo.nix ./mrjam-gateway.nix ];
  services.mrjamInventory.enable = false;
  # Observed identity pins the inactive candidate. The report is unauthenticated;
  # the exact adoption preflight and the complete host qualification still apply.
  services.mrjamInventory.adoption = {
    inherit (target.inventory_adoption) uid gid;
  };
  services.mrjamInventory.publicKeys = [
    (lib.removeSuffix "\n" (builtins.readFile ../targets/keys/mrjam-inventory.pub))
  ];
  services.mrjamRust.enable = false;
  services.mrjamForgejo.enable = false;
  services.mrjamGateway.enable = false;
}
