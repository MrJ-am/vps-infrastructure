# NIX_PATH doit pointer vers le Nixpkgs de validation, sans modifier le VPS.
let
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
assert current.services.vision.bootstrapCommit == "b8d1de19be4bdc0db408820853239156117060ca";
assert builtins.elem "vision-auth" current.users.users.nginx.extraGroups;
assert current.systemd.services.postgresql-setup.postStart != "";
assert current.systemd.services.nginx.serviceConfig.ExecStart == extended.systemd.services.nginx.serviceConfig.ExecStart;
{
  currentDerivation = current.system.build.toplevel.drvPath;
  withAdditionalDatabaseDerivation = extended.system.build.toplevel.drvPath;
  sharedPostgresql17 = true;
  visionIsolated = true;
}
