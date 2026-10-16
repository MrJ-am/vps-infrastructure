# Keep the complete observed production configuration as the base.
# Its old generations, secrets and services are neither copied nor reconstructed.
{ baseConfiguration, timerConfiguration ? baseConfiguration, kanidmApi ? ../../scripts/kanidm-api-privee.py }:
{ lib, ... }:
let
  base = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; modules = [ baseConfiguration ];
  }).config;
  timers = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; modules = [ timerConfiguration ];
  }).config;
in {
  imports = [ baseConfiguration ./module.nix ];
  _module.args.forgejoKanidmApi = kanidmApi;
  infrastructure.forgejo.enable = true;
  infrastructure.forgejo.sso.enable = true;
  # Production includes a priority-20 override and a catch-all reject. Insert this
  # socket/DB/Unix-user triple; leave every existing HBA rule byte-for-byte intact.
  services.postgresql.authentication = lib.mkOverride 10
    ("local forgejo forgejo peer\n" + base.services.postgresql.authentication);
  # NixOS distributes renewal dates over the certificate set. Keep every
  # pre-existing timer exactly as observed when adding this certificate.
  systemd.timers = lib.mapAttrs (_: timer: {
    timerConfig.OnCalendar = lib.mkOverride 10 timer.timerConfig.OnCalendar;
  }) (lib.filterAttrs (name: _: lib.hasPrefix "acme-renew-" name) timers.systemd.timers);
  systemd.units = lib.mapAttrs (_: unit: { text = lib.mkOverride 10 unit.text; })
    (lib.filterAttrs (name: _: lib.hasPrefix "acme-renew-" name && lib.hasSuffix ".timer" name) timers.systemd.units);
}
