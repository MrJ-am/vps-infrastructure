{ config, lib, pkgs, ... }:
let
  cfg = config.infrastructure.identite;
  realm = pkgs.writeText "mrjam-realm.json" (builtins.toJSON
    ((builtins.fromJSON (builtins.readFile ../operations/identite/realm.json)) // {
      registrationAllowed = cfg.inscriptionsOuvertes;
    }));
in {
  options.infrastructure.identite = {
    enable = lib.mkEnableOption "Identité commune OIDC MrJ.am (migration explicite)";
    inscriptionsOuvertes = lib.mkEnableOption "inscriptions après validation juridique et SMTP";
    preconditionsValidees = lib.mkEnableOption "preuve de restauration, identité initiale et notice validées";
    secretClient = lib.mkOption { type = lib.types.str; default = "/var/lib/mrjam-identite/oidc-client.secret"; };
    importInitial = lib.mkOption { type = lib.types.str; default = "/var/lib/mrjam-identite/mrjam-realm.json"; };
    sauvegardesJours = lib.mkOption { type = lib.types.ints.between 1 90; default = 30; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [ {
      assertion = cfg.preconditionsValidees;
      message = "Identité : fournir la preuve de migration/restauration avant activation.";
    } ];
    # JDBC passe par junixsocket : PostgreSQL conserve listen_addresses=''.
    services.keycloak = {
      enable = true;
      plugins = with pkgs.keycloak.plugins; [ junixsocket-common junixsocket-native-common ];
      database = { type = "postgresql"; host = "/run/postgresql"; createLocally = false;
        name = "mrjam_identite"; username = "keycloak"; passwordFile = null; };
      # Le chemin de credential reste dans la dérivation, son contenu privé
      # demeure hors store. L'import Keycloak ignore un realm déjà présent.
      realmFiles = [ "/run/credentials/keycloak.service/realm-import" ];
      settings = {
        hostname = "https://compte.mrj.am";
        http-enabled = true; http-host = "127.0.0.1"; http-port = 8085;
        proxy-headers = "xforwarded"; hostname-strict = true;
        health-enabled = true; metrics-enabled = false;
        log-level = "warn";
        spi-password-hashing--argon2--memory = "19456";
        spi-password-hashing--argon2--iterations = "2";
        spi-password-hashing--argon2--parallelism = "1";
      };
    };
    systemd.services.keycloak = {
      environment.JAVA_OPTS_APPEND = "-Xms256m -Xmx1200m";
      serviceConfig.MemoryMax = "2G";
      serviceConfig.LoadCredential = [ "realm-import:${cfg.importInitial}" ];
      serviceConfig.LogNamespace = "identite";
      after = [ "postgresql-setup.service" ];
      requires = [ "postgresql-setup.service" ];
      # L'import initial est préparé hors store avec le secret client injecté
      # par le workflow. Aucun secret ne figure dans realm.json.
    };
    services.postgresql.ensureDatabases = [ "mrjam_identite" ];
    services.postgresql.ensureUsers = [ { name = "keycloak"; ensureDBOwnership = false;
      ensureClauses = { login = true; superuser = false; createdb = false; createrole = false; bypassrls = false; }; } ];
    systemd.services.postgresql-setup.postStart = lib.mkAfter ''
      ${config.services.postgresql.package}/bin/psql -X --set=ON_ERROR_STOP=1 --dbname=postgres \
        --command='ALTER DATABASE mrjam_identite OWNER TO keycloak; REVOKE ALL ON DATABASE mrjam_identite FROM PUBLIC; GRANT CONNECT ON DATABASE mrjam_identite TO keycloak;'
    '';
    services.postgresql.identMap = "mrj_identite mrj-auth vision_identite";
    services.nginx.virtualHosts."compte.mrj.am" = {
      enableACME = true; forceSSL = true;
      extraConfig = ''
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header Referrer-Policy "no-referrer" always;
        access_log off;
      '';
      locations = {
        "/realms/mrjam/" = {
          proxyPass = "http://127.0.0.1:8085";
          extraConfig = ''
            client_max_body_size 64k;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Host $host;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header Forwarded "";
            limit_req zone=protected_api_per_ip burst=20 nodelay;
          '';
        };
        "/resources/".proxyPass = "http://127.0.0.1:8085";
        # Console maître, API admin et métriques accessibles en maintenance
        # par Actions, jamais par un administrateur d'application.
        "/".return = "404";
      };
    };
    environment.etc."mrjam/realm-sans-secret.json".source = realm;
    environment.etc."systemd/journald@identite.conf".text = ''
      [Journal]
      Storage=persistent
      Compress=yes
      SystemMaxUse=32M
      SystemMaxFileSize=4M
      RuntimeMaxUse=8M
      MaxRetentionSec=14day
      MaxFileSec=1day
      ForwardToSyslog=no
      ForwardToConsole=no
    '';
    # La clé privée de restauration n'est jamais stockée dans le store.
    # La possession de cette clé et une restauration réelle sont des
    # préconditions de l'activation, distinctes de l'évaluation de ce module.
    systemd.services.mrjam-sauvegarde = {
      description = "Sauvegardes chiffrées de Vision et de l'identité commune";
      after = [ "postgresql.service" ];
      serviceConfig = { Type = "oneshot"; User = "root"; UMask = "0077";
        NoNewPrivileges = true; PrivateTmp = true; ProtectHome = true; ProtectSystem = "strict";
        ReadWritePaths = [ "/var/backup/mrjam" ]; };
      script = ''
        set -euo pipefail
        jour=$(${pkgs.coreutils}/bin/date -u +%Y-%m-%dT%H%M%SZ)
        destination=/var/backup/mrjam
        temporaire=$(${pkgs.coreutils}/bin/mktemp -d)
        trap '${pkgs.coreutils}/bin/rm -rf "$temporaire"' EXIT
        recipient='${config.services.vision.backupRecipient}'
        for base in vision mrjam_identite; do
          ${pkgs.util-linux}/bin/runuser -u postgres -- ${config.services.postgresql.package}/bin/pg_dump --format=custom "$base" | \
            ${pkgs.age}/bin/age -r "$recipient" > "$destination/$base-$jour.age.tmp"
          ${pkgs.coreutils}/bin/mv "$destination/$base-$jour.age.tmp" "$destination/$base-$jour.age"
        done
        ${pkgs.sqlite}/bin/sqlite3 /var/lib/mrj-auth/sessions.sqlite ".backup '$temporaire/sessions.sqlite'"
        ${pkgs.age}/bin/age -r "$recipient" "$temporaire/sessions.sqlite" > "$destination/sessions-$jour.age.tmp"
        ${pkgs.coreutils}/bin/mv "$destination/sessions-$jour.age.tmp" "$destination/sessions-$jour.age"
        if test -f /var/lib/vision-effacements/demandes.jsonl; then
          ${pkgs.age}/bin/age -r "$recipient" /var/lib/vision-effacements/demandes.jsonl > "$destination/effacements-$jour.age.tmp"
          ${pkgs.coreutils}/bin/mv "$destination/effacements-$jour.age.tmp" "$destination/effacements-$jour.age"
        fi
        ${pkgs.findutils}/bin/find "$destination" -maxdepth 1 -type f -name '*.age' -mmin +${toString (cfg.sauvegardesJours * 1440)} -delete
      '';
    };
    systemd.tmpfiles.rules = [ "d /var/backup/mrjam 0700 root root -" ];
    systemd.timers.mrjam-sauvegarde = { wantedBy = [ "timers.target" ];
      timerConfig = { OnCalendar = "daily"; Persistent = true; RandomizedDelaySec = "30m"; }; };
  };
}
