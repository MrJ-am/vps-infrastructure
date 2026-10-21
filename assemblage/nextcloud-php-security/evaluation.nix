{ configuration }:
let
  e = import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ configuration ];
  };
  c = e.config;
in {
  generation = toString c.system.build.toplevel;
  errors = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
  units = builtins.mapAttrs (_: u: u.text) c.systemd.units;
  hosts = builtins.mapAttrs (_: v: {
    root = toString v.root;
    locations = builtins.attrNames v.locations;
    extra = v.extraConfig;
  }) c.services.nginx.virtualHosts;
  nginx = c.systemd.services.nginx.serviceConfig.ExecStart;
  fpm = c.systemd.services.phpfpm-nextcloud.serviceConfig.ExecStart;
  php = toString c.services.phpfpm.pools.nextcloud.phpPackage;
  phpVersion = c.services.nextcloud.phpPackage.version;
  nc = {
    package = toString c.services.nextcloud.package;
    apps = builtins.mapAttrs (_: a: toString a) c.services.nextcloud.extraApps;
    settings = c.services.nextcloud.settings;
    pool = c.services.nextcloud.poolSettings;
  };
  kanidm = toString c.services.kanidm.package;
  postgres = toString c.services.postgresql.finalPackage;
  age = toString e.pkgs.age;
  recipient = c.services.vision.backupRecipient;
}
