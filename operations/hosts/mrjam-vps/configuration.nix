# Explicit preparation entrypoint. The machine module has a hard activation
# gate: selecting this file must not silently replace the current host.
{
  imports = [ ./machine.nix ../../nixos/vps-preparation.nix ../../nixos/mrjam-vise.nix
    ../../nixos/mrjam-nextcloud-guards.nix ];
  services.mrjamVise.enable = false;
}
