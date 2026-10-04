{ config, lib, pkgs, ... }:
let
  projects = config.infrastructure.postgresql.projects;
  layout = import ../lib/databases.nix projects;
  permissions = pkgs.writeText "vps-postgresql-permissions.sql" layout.permissionsSQL;
in {
  options.infrastructure.postgresql.visionSemantique = lib.mkEnableOption
    "pgvector pour l'anti-doublon Vision (activation après audit et restauration isolée)";
  options.infrastructure.postgresql.projects = lib.mkOption {
    type = lib.types.attrsOf (lib.types.submodule {
      options.name = lib.mkOption {
        type = lib.types.str;
        description = "Nom commun de la base, du rôle et du compte système applicatif.";
      };
    });
    default = builtins.fromJSON (builtins.readFile ../databases.json);
    description = "Bases attribuées par l'infrastructure ; registre indépendant des sites HTTP.";
  };

  config = {
    assertions = map (name: {
      assertion = builtins.hasAttr name config.users.users && config.users.users.${name}.isSystemUser;
      message = "PostgreSQL : le projet doit déclarer le compte système dédié ${name}.";
    }) layout.databases;

    services.postgresql = {
      enable = true;
      # Conserver la version majeure et le dataDir existants lors du transfert.
      package = pkgs.postgresql_17;
      extensions = ps: lib.optional config.infrastructure.postgresql.visionSemantique ps.pgvector;
      enableTCPIP = false;
      settings = {
        listen_addresses = lib.mkForce "";
        unix_socket_directories = "/run/postgresql";
      };
      authentication = lib.mkForce layout.authentication;
      ensureDatabases = layout.databases;
      ensureUsers = layout.users;
    };

    # Exécuté après la création des bases/rôles, à chaque démarrage du setup,
    # y compris sur un cluster existant : initialScript ne conviendrait pas.
    systemd.services.postgresql-setup.postStart = ''
      ${config.services.postgresql.package}/bin/psql -X --set=ON_ERROR_STOP=1 \
        --host=/run/postgresql --dbname=postgres --file=${permissions}
    '' + lib.optionalString config.infrastructure.postgresql.visionSemantique ''
      # pgvector n'est pas une extension trusted : installation par postgres,
      # dans la seule base Vision, sans élargir les droits du rôle applicatif.
      ${config.services.postgresql.package}/bin/psql -X --set=ON_ERROR_STOP=1 \
        --host=/run/postgresql --dbname=vision \
        --command='CREATE EXTENSION IF NOT EXISTS vector;'
    '';

    services.postgresqlBackup = {
      enable = layout.databases != [];
      databases = layout.databases;
      backupAll = false;
      startAt = "daily";
      location = "/var/backup/postgresql";
    };
  };
}
