{ config, lib, pkgs, ... }:
let
  cfg = config.infrastructure.metier;
  cred = nom: "/run/credentials/mrjam-metier.service/${nom}";
  socket = "/run/mrjam-metier/http.sock";
  upstream = "http://unix:${socket}:";
  visionRoutes = [ "/" "/api/" "/api/web/" "/api/gestion/" "= /mcp"
    "= /api/web/effacer_compte" "= /api/v1/mobile-live-test"
    "= /auth/admission" "= /auth/admission/apercu" "= /auth/admission/confirmer" ];
  # Garder les auth_request, CSRF et limites déjà qualifiés ; seul le transport
  # devient commun. Tous les en-têtes de service sont imposés par Nginx.
  visionLocations = builtins.listToAttrs (map (route: {
    name = route;
    value = {
      proxyPass = lib.mkForce upstream;
      extraConfig = lib.mkAfter (''
        proxy_set_header X-Mrjam-Service "vision";
      '' + lib.optionalString (route != "/api/gestion/") ''
        proxy_set_header X-Vision-Administration "";
      '');
    };
  }) visionRoutes);
in {
  options.infrastructure.metier = {
    enable = lib.mkEnableOption "serveur métier SBCL commun, après qualification de l'assemblage";
    paquet = lib.mkOption { type = lib.types.nullOr lib.types.package; default = null; };
    bankVersion = lib.mkOption { type = lib.types.str; default = ""; };
    documentVision = lib.mkOption { type = lib.types.str; default = "/srv/vision/current/docs"; };
    ressourcesMatheval = lib.mkOption { type = lib.types.str; default = "/srv/matheval/current/docs/site"; };
    setupHash = lib.mkOption { type = lib.types.str; default = "/var/lib/mrjam-metier/secrets/matheval-setup-hash"; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = cfg.paquet != null && builtins.match "[A-Za-z0-9._-]+" cfg.bankVersion != null;
        message = "Le serveur commun exige un paquet assemblé exact et un corpus qualifié."; }
      { assertion = config.infrastructure.identite.enable && config.infrastructure.visionMultiutilisateur.enable
          && config.infrastructure.visionCycle.enable && config.infrastructure.admission.enable && config.infrastructure.fermeture.enable;
        message = "L'étape 1 conserve l'identité actuelle et intègre tous les auxiliaires qualifiés."; }
    ];
    users.groups.mrjam-ingress = {};
    users.users.mrjam-metier = { isSystemUser = true; group = "mrjam-ingress"; };
    users.users.nginx.extraGroups = [ "mrjam-ingress" ];
    # Ces comptes historiques ne sont pas créés par bibliothèque : leur maintien
    # préserve les propriétaires Unix, sauvegardes et possibilités de retour.
    services.postgresql.identMap = lib.mkAfter (lib.concatStringsSep "\n"
      (map (role: "mrjam_metier mrjam-metier ${role}")
        [ "vision" "vision_administration" "vision_cycle" "vision_admission" "vision_fermeture" "vision_entretien" "matheval_app" ]));
    systemd.services = lib.genAttrs
      [ "vision" "matheval" "vision-migrate" "vision-gestion" "vision-cycle" "mrjam-admission" "mrjam-fermeture" "mrjam-courriel" "vision-purge" ]
      (_: { enable = lib.mkForce false; }) // {
      mrjam-metier = {
        description = "Bibliothèques métier Vision/Matheval, HTTP/MCP et tâches communes";
        wantedBy = [ "multi-user.target" ];
        after = [ "postgresql.service" "postgresql-setup.service" "keycloak.service" ];
        requires = [ "postgresql.service" "postgresql-setup.service" ];
        environment = {
          MRJAM_LIBCRYPTO = "${lib.getLib pkgs.openssl}/lib/libcrypto.so.3";
          MRJAM_LIBPQ = "${lib.getLib config.services.postgresql.package}/lib/libpq.so.5";
          MRJAM_LIBSQLITE = "${lib.getLib pkgs.sqlite}/lib/libsqlite3.so.0";
          MRJAM_CURL = "${pkgs.curl}/bin/curl";
          MRJAM_CA_FILE = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";
          MRJAM_SOCKET = socket;
          AGE = "${pkgs.age}/bin/age";
          VISION_DSN = "host=/run/postgresql dbname=vision user=vision options='-c statement_timeout=5000'";
          VISION_GESTION_DSN = "host=/run/postgresql dbname=vision user=vision_administration options='-c statement_timeout=5000'";
          VISION_CYCLE_DSN = "host=/run/postgresql dbname=vision user=vision_cycle options='-c statement_timeout=5000'";
          VISION_ENTRETIEN_DSN = "host=/run/postgresql dbname=vision user=vision_entretien options='-c statement_timeout=10000'";
          VISION_DOCUMENT_ROOT = cfg.documentVision;
          VISION_CURL = "${pkgs.curl}/bin/curl";
          VISION_EMBEDDINGS_URL = "http://127.0.0.1:39004/embedding";
          VISION_VERSION = "2.7.0";
          VISION_REGISTRE_EFFACEMENTS = "/var/lib/mrjam-metier/effacements/demandes.jsonl";
          VISION_CYCLE_ETAT = "/var/lib/mrjam-metier/cycle/";
          VISION_CYCLE_CLIENT_SECRET = cred "cycle-client";
          VISION_CYCLE_CONFIG = cred "cycle-config";
          MATHEVAL_DSN = "host=/run/postgresql dbname=matheval user=matheval_app options='-c statement_timeout=5000'";
          MATHEVAL_BANK_VERSION = cfg.bankVersion;
          MATHEVAL_ORIGIN = "https://principiipetit.io";
          MATHEVAL_SETUP_HASH_FILE = cred "matheval-setup";
          MRJ_SMTP_SECRET = cred "smtp";
          MRJ_COURRIEL_FILE = "/var/lib/mrjam-metier/courriel/file.sqlite";
          MRJ_ADMISSION_DSN = "host=/run/postgresql dbname=vision user=vision_admission options='-c statement_timeout=5000'";
          MRJ_ADMISSION_ETAT = "/var/lib/mrjam-metier/admission/";
          MRJ_ADMISSION_SECRET = cred "admission-client";
          MRJ_FERMETURE_DSN = "host=/run/postgresql dbname=vision user=vision_fermeture options='-c statement_timeout=5000'";
          MRJ_FERMETURE_ETAT = "/var/lib/mrjam-metier/fermeture/";
          MRJ_FERMETURE_CONFIG = cred "cycle-config";
          MRJ_FERMETURE_CLIENT = cred "fermeture-client";
          MRJ_FERMETURE_HOOK = cred "fermeture-hook";
        };
        serviceConfig = {
          Type = "simple"; User = "mrjam-metier"; Group = "mrjam-ingress";
          ExecStart = pkgs.writeShellScript "mrjam-metier-demarrer" ''
            set -eu
            export MRJAM_INGRESS_UID=$(${pkgs.coreutils}/bin/id -u nginx)
            exec ${cfg.paquet}/bin/mrjam-metier
          '';
          RuntimeDirectory = "mrjam-metier"; RuntimeDirectoryMode = "0750";
          StateDirectory = "mrjam-metier"; StateDirectoryMode = "0700";
          LoadCredential = [ "smtp:${config.infrastructure.courriel.secret}"
            "cycle-config:${config.infrastructure.visionCycle.configPrivee}"
            "cycle-client:${config.infrastructure.visionCycle.secretClient}"
            "admission-client:${config.infrastructure.admission.secretClient}"
            "fermeture-client:${config.infrastructure.fermeture.secretClient}"
            "fermeture-hook:${config.infrastructure.fermeture.secretHook}"
            "matheval-setup:${cfg.setupHash}" ];
          Restart = "on-failure"; RestartSec = 3; TimeoutStopSec = 30; UMask = "0077";
          NoNewPrivileges = true; PrivateTmp = true; PrivateDevices = true;
          ProtectSystem = "strict"; ProtectHome = true; ProtectKernelTunables = true;
          ProtectKernelModules = true; ProtectKernelLogs = true; ProtectControlGroups = true;
          ProtectClock = true; ProtectHostname = true; ProtectProc = "invisible"; ProcSubset = "pid";
          RestrictSUIDSGID = true; RestrictRealtime = true; CapabilityBoundingSet = "";
          RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
          TasksMax = 128; MemoryMax = "1G";
        };
      };
    };
    systemd.timers.vision-purge.enable = lib.mkForce false;
    systemd.timers.mrjam-courriel.enable = lib.mkForce false;
    services.nginx.virtualHosts."vision.mrj.am".locations = visionLocations;
    services.nginx.virtualHosts."principiipetit.io".locations = {
      "/matheval/" = {
        proxyPass = lib.mkForce null;
        alias = "${cfg.ressourcesMatheval}/";
        index = "index.html";
        extraConfig = lib.mkForce ''
          add_header X-Content-Type-Options "nosniff" always;
          add_header Referrer-Policy "no-referrer" always;
        '';
      };
      "^~ /matheval/api/" = {
        proxyPass = upstream;
        extraConfig = ''
          client_max_body_size 5m;
          proxy_set_header X-Mrjam-Service "matheval";
          proxy_set_header X-Mrj-User "";
          proxy_set_header X-Vision-Authenticated "";
          proxy_set_header X-Vision-Browser "";
          proxy_set_header X-Vision-Administration "";
          proxy_set_header Host $host;
          proxy_set_header X-Forwarded-Proto $scheme;
          limit_req zone=protected_api_per_ip burst=10 nodelay;
          limit_req_status 429;
        '';
      };
    };
    # Le hook provisoire Keycloak exige en plus son secret constant-time.
    # Aucun domaine public ni écoute autre que le loopback pour ce chemin.
    services.nginx.virtualHosts."mrjam-fermeture-interne" = {
      listen = [{ addr = "127.0.0.1"; port = 3028; ssl = false; }];
      enableACME = false; forceSSL = false; serverName = "_";
      locations."= /fermer" = {
        proxyPass = upstream;
        extraConfig = ''
          client_max_body_size 1k;
          access_log off;
          proxy_set_header X-Mrjam-Service "fermeture-interne";
          proxy_set_header X-Mrj-User "";
          proxy_set_header X-Vision-Authenticated "";
          proxy_set_header X-Vision-Browser "";
          proxy_set_header X-Vision-Administration "";
          proxy_set_header Cookie "";
        '';
      };
      locations."/".return = "404";
    };
  };
}
