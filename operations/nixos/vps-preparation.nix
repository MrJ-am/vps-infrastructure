# Composition prepared in the authoritative VPS repository. This is not a host
# definition: no hardware, network, stateVersion, key or current service is guessed.
{ ... }: {
  imports = [ ./mrjam-inventory.nix ./mrjam-rust.nix ./mrjam-forgejo.nix ];
  services.mrjamInventory.enable = false;
  services.mrjamRust.enable = false;
  services.mrjamForgejo.enable = false;
}
