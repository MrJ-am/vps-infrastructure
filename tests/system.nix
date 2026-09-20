# NIX_PATH doit pointer vers le Nixpkgs de validation, sans modifier le VPS.
let
  lib = import <nixpkgs/lib>;
  evaluate = extra: (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ ../hosts/hostinger/configuration.nix extra ];
  }).config;
  current = evaluate {};
  extended = evaluate ({ lib, ... }: {
    infrastructure.postgresql.projects = lib.mkForce {
      matheval.name = "matheval";
      vision.name = "vision";
      example.name = "example";
    };
    users.groups.example = {};
    users.users.example = { isSystemUser = true; group = "example"; };
  });
  valid = config: builtins.all (entry: entry.assertion) config.assertions;
in
assert valid current && valid extended;
assert current.services.postgresql.package.psqlSchema == "17";
assert current.services.postgresql.dataDir == "/var/lib/postgresql/17";
assert current.services.postgresql.settings.listen_addresses == "";
assert !current.services.postgresql.enableTCPIP;
assert current.services.postgresqlBackup.databases == [ "matheval" "vision" ];
assert extended.services.postgresqlBackup.databases == [ "example" "matheval" "vision" ];
assert current.services.postgresqlBackup.location == "/var/backup/postgresql";
assert builtins.elem "postgresql-setup.service" current.systemd.services.matheval.requires;
assert current.systemd.services.matheval.serviceConfig.User == "matheval";
assert current.systemd.services.matheval.serviceConfig.EnvironmentFile == "/var/lib/matheval/secrets.env";
assert builtins.elem "vision-migrate.service" current.systemd.services.vision.requires;
assert current.systemd.services.vision.serviceConfig.User == "vision";
assert current.systemd.services.vision.environment.PORT == "3001";
assert current.systemd.services.vision.environment.PGDATABASE == "vision";
assert current.systemd.services.vision.environment.PGUSER == "vision";
assert current.services.vision.version == "1.2.0";
assert current.services.vision.bootstrapCommit == "445f9d7e6944d621de33283ca960d772813f47a2";
assert lib.hasSuffix
  "/bin/psql"
  current.systemd.services.vision.environment.VISION_PSQL;
assert builtins.elem
  "d /var/lib/vision 0710 root vision-auth -"
  current.systemd.tmpfiles.rules;
assert lib.hasSuffix
  "/bin/dash /srv/vision/current/scripts/migrate.sh"
  current.systemd.services.vision-migrate.serviceConfig.ExecStart;
assert builtins.elem "vision-auth" current.users.users.nginx.extraGroups;
assert lib.hasInfix
  "auth_basic_user_file /var/lib/vision/auth/htpasswd;"
  current.services.nginx.virtualHosts."vision.mrj.am".locations."= /mcp".extraConfig;
assert lib.hasInfix
  "proxy_set_header X-Vision-Authenticated \"1\";"
  current.services.nginx.virtualHosts."vision.mrj.am".locations."= /mcp".extraConfig;
assert lib.hasInfix
  "proxy_buffering off;"
  current.services.nginx.virtualHosts."vision.mrj.am".locations."= /mcp".extraConfig;
assert builtins.elem
  "f+ /var/lib/vision/auth/mobile-live-test.htpasswd 0640 root vision-auth - mobile-live:$6$M0bLive26$eKajMiudVvi4/NSD3YFmHxun73Wiv5rR750TUzt.dwrT5urrD07wQ4kP9VB8hrmDJogaGiH7mYnQC75GplKtL1"
  current.systemd.tmpfiles.rules;
assert lib.hasInfix
  "auth_basic_user_file /var/lib/vision/auth/mobile-live-test.htpasswd;"
  current.services.nginx.virtualHosts."vision.mrj.am".locations."= /api/v1/mobile-live-test".extraConfig;
assert lib.hasInfix
  "proxy_set_header X-Vision-Authenticated \"1\";"
  current.services.nginx.virtualHosts."vision.mrj.am".locations."= /api/v1/mobile-live-test".extraConfig;
assert lib.hasInfix
  "add_header Strict-Transport-Security \"max-age=31536000\" always;"
  current.services.nginx.virtualHosts."vision.mrj.am".locations."= /api/v1/mobile-live-test".extraConfig;
assert lib.hasInfix
  "return 401"
  current.services.nginx.virtualHosts."vision.mrj.am".locations."@vision-mobile-live-test-authentication-required".extraConfig;
assert current.systemd.services.postgresql-setup.postStart != "";
assert current.systemd.services.nginx.serviceConfig.ExecStart == extended.systemd.services.nginx.serviceConfig.ExecStart;
{
  currentDerivation = current.system.build.toplevel.drvPath;
  withAdditionalDatabaseDerivation = extended.system.build.toplevel.drvPath;
  sharedPostgresql17 = true;
  visionIsolated = true;
}
