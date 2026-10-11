{ config, lib, pkgs, ... }:
let
  projects = config.infrastructure.postgresql.projects;
  layout = import ../lib/databases.nix projects;
  multi = config.infrastructure.visionMultiutilisateur.enable or false;
  identite = config.infrastructure.identite.enable or false;
  metier = config.infrastructure.metier.enable or false;
  permissions = pkgs.writeText "vps-postgresql-permissions.sql"
    (if multi then lib.replaceStrings
      [ ''GRANT USAGE, CREATE ON SCHEMA public TO "vision";'' ''GRANT CONNECT, TEMPORARY ON DATABASE "vision" TO "vision";'' ]
      [ ''GRANT USAGE ON SCHEMA public TO "vision";'' ''GRANT CONNECT ON DATABASE "vision" TO "vision";'' ]
      layout.permissionsSQL else layout.permissionsSQL);
in {
  options.infrastructure.postgresql.visionSemantique = lib.mkEnableOption
    "pgvector pour l'anti-doublon Vision (activation après audit et restauration isolée)";
  options.infrastructure.postgresql.projects = lib.mkOption {
    type = lib.types.attrsOf (lib.types.submodule {
      options.name = lib.mkOption {
        type = lib.types.str;
        description = "Nom historique de base et propriétaire ; identité Unix et rôles applicatifs gérés séparément.";
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
      authentication = lib.mkForce (
        lib.optionalString metier "local vision vision,vision_administration,vision_cycle,vision_admission,vision_fermeture,vision_entretien peer map=mrjam_metier\nlocal matheval matheval_app peer map=mrjam_metier\n" +
        lib.optionalString identite "local mrjam_identite keycloak peer\n" +
        lib.optionalString multi "local vision vision_identite peer map=mrj_identite\nlocal vision vision_administration peer\nlocal vision vision_cycle peer\nlocal vision vision_admission peer\nlocal vision vision_fermeture peer\n" +
        layout.authentication);
      ensureDatabases = layout.databases;
      ensureUsers = map (user: user // lib.optionalAttrs (multi && user.name=="vision") {
        ensureDBOwnership = false;
      }) layout.users;
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
      # Vision et l'identité suivent la sauvegarde chiffrée du nouveau module.
      databases = lib.filter (name: !multi || name != "vision") layout.databases;
      backupAll = false;
      startAt = "daily";
      location = "/var/backup/postgresql";
    };
  };
}
