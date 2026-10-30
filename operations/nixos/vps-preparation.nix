# Composition prepared in the authoritative VPS repository. This is not a host
# definition: no hardware, network, stateVersion, key or current service is guessed.
{ lib, ... }: {
  imports = [ ./mrjam-inventory.nix ./mrjam-rust.nix ./mrjam-forgejo.nix ];
  services.mrjamInventory.enable = false;
  # User-supplied public reference only; existing identity/adoption stay unqualified.
  services.mrjamInventory.publicKeys = [
    (lib.removeSuffix "\n" (builtins.readFile ../targets/keys/mrjam-inventory.pub))
  ];
  services.mrjamRust.enable = false;
  services.mrjamForgejo.enable = false;
}
