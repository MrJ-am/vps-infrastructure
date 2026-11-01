# Explicit preparation entrypoint. The machine module has a hard activation
# gate: selecting this file must not silently replace the current host.
{
  imports = [ ./machine.nix ../../nixos/vps-preparation.nix ../../nixos/mrjam-vise.nix
    ../../nixos/mrjam-nextcloud-guards.nix ../../nixos/mrjam-forgejo-host.nix
    ../../nixos/mrjam-kanidm-host.nix ../../nixos/mrjam-nextcloud-host.nix
    ./observed-service-identities.nix ];
  services.mrjamVise.enable = false;
}
