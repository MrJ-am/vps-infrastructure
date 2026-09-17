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
    };
    users.groups.vision = {};
    users.users.vision = { isSystemUser = true; group = "vision"; };
  });
  valid = config: builtins.all (entry: entry.assertion) config.assertions;
in
assert valid current && valid extended;
assert current.services.postgresql.package.psqlSchema == "17";
assert current.services.postgresql.dataDir == "/var/lib/postgresql/17";
assert current.services.postgresql.settings.listen_addresses == "";
assert !current.services.postgresql.enableTCPIP;
assert current.services.postgresqlBackup.databases == [ "matheval" ];
assert extended.services.postgresqlBackup.databases == [ "matheval" "vision" ];
assert current.services.postgresqlBackup.location == "/var/backup/postgresql";
assert builtins.elem "postgresql-setup.service" current.systemd.services.matheval.requires;
assert current.systemd.services.matheval.serviceConfig.User == "matheval";
assert current.systemd.services.matheval.serviceConfig.EnvironmentFile == "/var/lib/matheval/secrets.env";
assert current.systemd.services.postgresql-setup.postStart != "";
assert current.services.nginx.virtualHosts == extended.services.nginx.virtualHosts;
{
  # Force l'évaluation du système entier, sans le construire ni l'activer.
  currentDerivation = current.system.build.toplevel.drvPath;
  withVisionDerivation = extended.system.build.toplevel.drvPath;
  sharedPostgresql17 = true;
}
