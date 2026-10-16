# Keep the complete observed production configuration as the base.
# Its old generations, secrets and services are neither copied nor reconstructed.
{ baseConfiguration }:
{ lib, ... }:
let
  base = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; modules = [ baseConfiguration ];
  }).config;
in {
  imports = [ baseConfiguration ./module.nix ];
  infrastructure.forgejo.enable = true;
  # Production uses mkForce and an explicit catch-all reject. Insert only this
  # socket/DB/Unix-user triple; leave every existing HBA rule byte-for-byte intact.
  services.postgresql.authentication = lib.mkOverride 40
    ("local forgejo forgejo peer\n" + base.services.postgresql.authentication);
}
