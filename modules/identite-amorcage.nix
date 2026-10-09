{ config, lib, pkgs, ... }:
let
  cfg = config.infrastructure.amorcageIdentite;
  pg = config.services.postgresql.finalPackage;
  donnees = "/var/lib/mrjam-amorcage-postgresql";
  socket = "/run/mrjam-amorcage-postgresql";
  # Reprendre la dérivation optimisée réellement qualifiée, sans reconstruire
  # ses plugins avec une autre configuration de compilation.
  keycloak = import ../lib/keycloak-optimise.nix { inherit pkgs; };
  theme = pkgs.runCommand "mrjam-themes-amorcage" {} ''
    mkdir -p "$out"
    cp -R ${keycloak}/themes/. "$out/"
    mkdir -p "$out/mrjam"
    cp -R ${../services/keycloak-mrjam/theme}/. "$out/mrjam/"
  '';
  sources = import ../services/sources-mrjam.nix { inherit pkgs; };
in {
  options.infrastructure.amorcageIdentite.enable = lib.mkEnableOption
    "amorçage réservé de l'identité, dans un cluster indépendant de Vision";
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = !(config.infrastructure.identite.enable or false) &&
          !(config.infrastructure.visionMultiutilisateur.enable or false) &&
          !(config.infrastructure.admission.enable or false) &&
          !(config.infrastructure.fermeture.enable or false);
        message = "L'amorçage est distinct du mode commun et de toute admission."; }
      { assertion = config.services.postgresql.enable &&
          lib.versions.major config.services.postgresql.package.version == "17" &&
          !config.services.postgresql.enableTCPIP &&
          config.services.postgresql.settings.listen_addresses == "";
        message = "L'amorçage conserve le socle PostgreSQL17 sans TCP."; }
    ];
    # Aucun ensureDatabases/ensureUsers/HBA/owner sur l'instance de production.
    systemd.services.mrjam-amorcage-postgresql = {
      description = "Cluster privé de l'amorçage MrJ.am";
      wantedBy = [ "multi-user.target" ];
      before = [ "mrjam-amorcage-identite.service" ];
      preStart = ''
        ${pkgs.runtimeShell} ${../scripts/identite-amorcage-postgresql.sh} initialiser \
          ${pg}/bin ${donnees} ${socket}
      '';
      postStart = ''
        ${pkgs.runtimeShell} ${../scripts/identite-amorcage-postgresql.sh} configurer \
          ${pg}/bin ${donnees} ${socket}
      '';
      serviceConfig = {
        Type = "forking"; User = "postgres"; Group = "postgres"; UMask = "0077";
        StateDirectory = "mrjam-amorcage-postgresql"; StateDirectoryMode = "0700";
        RuntimeDirectory = "mrjam-amorcage-postgresql"; RuntimeDirectoryMode = "0711";
        PIDFile = "${donnees}/postmaster.pid";
        ExecStart = "${pg}/bin/pg_ctl -D ${donnees} -l ${donnees}/serveur-prive.log -w -o \"-c listen_addresses='' -c unix_socket_directories=${socket} -c unix_socket_permissions=0777 -c port=5432 -c shared_buffers=64MB -c max_connections=30\" start";
        ExecStop = "${pg}/bin/pg_ctl -D ${donnees} -w -m fast stop";
        KillMode = "mixed"; KillSignal = "SIGINT"; TimeoutStopSec = 45;
        NoNewPrivileges = true; PrivateTmp = true; PrivateDevices = true;
        ProtectSystem = "strict"; ProtectHome = true;
        ProtectKernelTunables = true; ProtectKernelModules = true;
        ProtectControlGroups = true; RestrictSUIDSGID = true;
        CapabilityBoundingSet = ""; RestrictAddressFamilies = [ "AF_UNIX" ];
        MemoryMax = "384M"; TasksMax = 64; LogNamespace = "identite";
      };
    };
    systemd.services.mrjam-amorcage-identite = {
      description = "Identité réservée à l'amorçage du propriétaire";
      wantedBy = [ "multi-user.target" ];
      after = [ "mrjam-amorcage-postgresql.service" ];
      requires = [ "mrjam-amorcage-postgresql.service" ];
      path = [ pkgs.coreutils ];
      serviceConfig = {
        Type = "notify"; NotifyAccess = "all"; DynamicUser = true;
        User = "keycloak"; Group = "keycloak"; RuntimeDirectoryMode = "0700";
        RuntimeDirectory = "mrjam-amorcage-identite";
        ExecStart = "${pkgs.runtimeShell} ${../scripts/identite-amorcage-demarrer.sh} ${keycloak} /run/mrjam-amorcage-identite ${socket} ${theme}";
        Restart = "on-failure"; RestartSec = 5; TimeoutStartSec = 180; TimeoutStopSec = 45;
        LoadCredential = [
          "realm-import:/var/lib/mrjam-identite/mrjam-realm.json"
          "amorcage-admin:/var/lib/mrjam-identite/amorcage-admin.secret"
        ];
        MemoryMax = "2G"; UMask = "0077"; LogNamespace = "identite";
        NoNewPrivileges = true; PrivateTmp = true; PrivateDevices = true;
        ProtectSystem = "strict"; ProtectHome = true;
        ProtectKernelTunables = true; ProtectKernelModules = true;
        ProtectControlGroups = true; RestrictSUIDSGID = true;
        CapabilityBoundingSet = ""; AmbientCapabilities = "";
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
      };
    };
    services.nginx.virtualHosts."log.mrj.am" = {
      enableACME = true; forceSSL = true;
      extraConfig = ''
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header Referrer-Policy "no-referrer" always;
        access_log off;
        error_log /dev/null;
      '';
      locations = {
        "= /realms/mrjam/clients-registrations".return = "404";
        "/realms/mrjam/clients-registrations/".return = "404";
        "/realms/mrjam/" = {
          proxyPass = "http://127.0.0.1:8085";
          extraConfig = ''
            client_max_body_size 64k;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Host $host;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Forwarded-Port 443;
            proxy_set_header X-Forwarded-Prefix "";
            proxy_set_header Forwarded "";
            limit_req zone=protected_api_per_ip burst=20 nodelay;
          '';
        };
        "/resources/".proxyPass = "http://127.0.0.1:8085";
        "= /code-source/services-mrjam.tar.gz" = {
          alias = "${sources}/services-mrjam.tar.gz";
          extraConfig = ''
            types {}
            default_type application/gzip;
            add_header Cache-Control "no-store" always;
          '';
        };
        "/".return = "404";
      };
    };
    environment.etc."systemd/journald@identite.conf".text = ''
      [Journal]
      Storage=persistent
      Compress=yes
      SystemMaxUse=32M
      SystemMaxFileSize=4M
      RuntimeMaxUse=8M
      MaxRetentionSec=30day
      MaxFileSec=1day
      ForwardToSyslog=no
      ForwardToConsole=no
    '';
    systemd.tmpfiles.rules = [ "d /var/backup/mrjam-amorcage 0700 root root -" ];
    systemd.services.mrjam-amorcage-sauvegarde = {
      description = "Copie locale chiffrée de l'identité d'amorçage";
      after = [ "mrjam-amorcage-postgresql.service" ];
      serviceConfig = { Type = "oneshot"; User = "root"; UMask = "0077";
        NoNewPrivileges = true; PrivateTmp = true; ProtectSystem = "strict";
        ProtectHome = true; ReadWritePaths = [ "/var/backup/mrjam-amorcage" ]; };
      script = ''
        set -euo pipefail
        jour=$(${pkgs.coreutils}/bin/date -u +%Y-%m-%dT%H%M%SZ)
        cible=/var/backup/mrjam-amorcage/identite-$jour.age
        trap '${pkgs.coreutils}/bin/rm -f -- "$cible.tmp"' EXIT
        ${pkgs.util-linux}/bin/runuser -u postgres -- ${pg}/bin/pg_dump -h ${socket} -U postgres -p 5432 -d mrjam_identite --format=custom | \
          ${pkgs.age}/bin/age -r '${config.services.vision.backupRecipient}' > "$cible.tmp"
        ${pkgs.coreutils}/bin/mv "$cible.tmp" "$cible"
        ${pkgs.findutils}/bin/find /var/backup/mrjam-amorcage -maxdepth 1 -type f -name '*.age' -mmin +43200 -delete
      '';
    };
    systemd.timers.mrjam-amorcage-sauvegarde = {
      wantedBy = [ "timers.target" ];
      timerConfig = { OnCalendar = "daily"; Persistent = true; RandomizedDelaySec = "30m"; };
    };
  };
}
