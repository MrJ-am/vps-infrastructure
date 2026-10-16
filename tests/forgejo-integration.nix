# Pure integration regression: old priority-20 HBA override and ACME schedules.
# Evaluate with the Nixpkgs revision pinned in assemblage/forgejo/versions.json.
{ nixpkgs }:
let
  evaluate = modules: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux"; inherit modules;
  }).config;
  base = { lib, pkgs, ... }: {
    imports = [ ../assemblage/forgejo/module.nix ];
    options.services.vision.backupRecipient = lib.mkOption {
      type = lib.types.str;
      default = "age1p95t4z0aafq7j4fl7cc9f0cjz8j03dtlmz56kec4lj6vwxrvzpqqnc53cc";
    };
    config = {
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/vda"; fsType = "ext4"; };
      system.stateVersion = "26.05";
      services.postgresql = {
        enable = true; package = pkgs.postgresql_17;
        authentication = lib.mkOverride 20 "local all postgres peer\nlocal all all reject\n";
      };
      services.nginx = {
        enable = true;
        virtualHosts."existing.example.org" = {
          enableACME = true; forceSSL = true; root = "/srv/test";
        };
      };
      security.acme = { acceptTerms = true; defaults.email = "admin@example.org"; };
    };
  };
  before = evaluate [ base ];
  after = evaluate [ (import ../assemblage/forgejo/integration.nix { baseConfiguration = base; }) ];
  peer = after.services.postgresql.authentication == "local forgejo forgejo peer\n" + before.services.postgresql.authentication;
  oldTimer = after.systemd.units."acme-renew-existing.example.org.timer".text == before.systemd.units."acme-renew-existing.example.org.timer".text;
  errors = map (a: a.message) (builtins.filter (a: !a.assertion) after.assertions);
in assert peer; assert oldTimer; assert errors == []; {
  inherit peer oldTimer errors;
  nginxConfigDrv = builtins.head (builtins.filter (path: (import (nixpkgs + "/lib")).hasSuffix "-nginx.conf.drv" path)
    (builtins.attrNames (builtins.getContext after.systemd.services.nginx.serviceConfig.ExecStart)));
  system = after.system.build.toplevel.drvPath;
}
