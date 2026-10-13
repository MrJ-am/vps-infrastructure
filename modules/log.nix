{ config, lib, pkgs, ... }:
let
  cfg = config.infrastructure.log;
  socket = "http://unix:/run/mrjam-metier/http.sock:";
  logHeaders = ''
    proxy_set_header X-Mrjam-Service "log";
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Origin $http_origin;
  '';
  commun = logHeaders + ''
    proxy_set_header Host $host;
    proxy_set_header Authorization "";
    access_log off;
    client_max_body_size 8k;
  '';
  auth = chemin: extra: { proxyPass = lib.mkForce (socket + chemin); extraConfig = lib.mkForce (commun + extra); };
  verifier = chemin: variable: auth chemin ''
    internal;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header X-Original-Method ${variable};
    proxy_set_header X-CSRF-Token $http_x_csrf_token;
  '';
in {
  options.infrastructure.log = {
    enable = lib.mkEnableOption "Kanidm séparé et client Log Common Lisp qualifiés";
    paquet = lib.mkOption { type = lib.types.nullOr lib.types.package; default = null; };
    secretClient = lib.mkOption { type = lib.types.str; default = "/var/lib/mrjam-identite/kanidm-vision.secret"; };
    secretAdmission = lib.mkOption { type = lib.types.str; default = "/var/lib/mrjam-identite/kanidm-admission.token"; };
  };
  imports = [ (import ../assemblage/kanidm/service.nix {
    tlsChainFile = "/var/lib/acme/log.mrj.am/fullchain.pem";
    tlsKeyFile = "/var/lib/acme/log.mrj.am/key.pem";
  }) ];
  config = lib.mkMerge [ {
    services.kanidm.server.enable = lib.mkForce cfg.enable;
    systemd.services.kanidm.enable = lib.mkForce cfg.enable;
  } (lib.mkIf cfg.enable {
    assertions = [{ assertion = config.infrastructure.metier.enable && cfg.paquet != null;
      message = "Log exige les deux paquets propres qualifiés, sans outil de développement."; }];
    services.kanidm.package = lib.mkForce cfg.paquet;
    services.kanidm.server.settings.adminbindpath = "/run/kanidmd/admin.sock";
    services.kanidm.server.settings.online_backup.versions = lib.mkForce 0;
    systemd.services.kanidm.serviceConfig.AmbientCapabilities = lib.mkForce [];
    systemd.services.kanidm.serviceConfig.RuntimeDirectoryMode = "0700";
    services.kanidm.server.settings.log_level = "info";
    services.nginx.virtualHosts."log.mrj.am".extraConfig = lib.mkAfter ''
      # Les URL d'enrôlement peuvent porter un secret. Ne pas journaliser l'URI
      # dans une erreur de proxy ; les sondes d'exploitation donnent l'état.
      error_log /dev/null emerg;
    '';
    systemd.tmpfiles.rules = [ "d /var/lib/kanidm/backups 0700 kanidm kanidm -" ];
    systemd.services.mrjam-sauvegarde.serviceConfig.ReadWritePaths = lib.mkAfter [ "/var/lib/kanidm/backups" ];
    systemd.services.mrjam-sauvegarde.after = lib.mkAfter [ "kanidm.service" ];
    systemd.services.mrjam-sauvegarde.requires = lib.mkAfter [ "kanidm.service" ];
    security.acme.certs."log.mrj.am".reloadServices = [ "nginx" "kanidm" ];
    services.keycloak.enable = lib.mkForce false;
    systemd.services.keycloak.enable = lib.mkForce false;
    systemd.services.mrj-auth.enable = lib.mkForce false;
    # Les comptes Unix/bases historiques restent des points de retour, inactifs.
    services.postgresql.identMap = lib.mkOrder 1700 "mrj_identite mrjam-metier vision_identite";
    systemd.services.mrjam-metier = {
      after = lib.mkForce [ "postgresql.service" "postgresql-setup.service" "kanidm.service" ];
      environment = {
        MRJ_LOG_DATABASE = "/var/lib/mrjam-metier/log/sessions.sqlite";
        MRJ_LOG_IDENTITES_DSN = "host=/run/postgresql dbname=vision user=vision_identite options='-c statement_timeout=5000'";
        MRJ_LOG_CLIENT_SECRET = "/run/credentials/mrjam-metier.service/log-client";
        MRJ_ADMISSION_SECRET = lib.mkForce "/run/credentials/mrjam-metier.service/native-admission";
      };
      serviceConfig.LoadCredential = lib.mkForce [
        "smtp:${config.infrastructure.courriel.secret}"
        "cycle-config:${config.infrastructure.visionCycle.configPrivee}"
        "matheval-setup:${config.infrastructure.metier.setupHash}"
        "native-admission:${cfg.secretAdmission}"
        "log-client:${cfg.secretClient}" ];
      # L'admission conserve ses contrôles/états avec une capacité native
      # onboarding, pas un credential administrateur IdP général.
      serviceConfig.UnsetEnvironment = [ "MRJ_FERMETURE_DSN"
        "VISION_CYCLE_CLIENT_SECRET" "MRJ_FERMETURE_CLIENT" "MRJ_FERMETURE_HOOK" ];
    };
    services.nginx.virtualHosts."vision.mrj.am".locations = {
      "/auth/" = auth "" ''limit_req zone=protected_api_per_ip burst=5 nodelay; limit_req_status 429;'';
      "= /_mrj_session" = verifier "/verify" "$mrj_original_method";
      "= /_vision_administration" = verifier "/verify-gestion" "$vision_gestion_method";
      "= /_vision_mcp_token" = {
        proxyPass = lib.mkForce (socket + "/verify-mcp");
        extraConfig = lib.mkForce (logHeaders + ''
          internal;
          proxy_pass_request_body off;
          proxy_set_header Content-Length "";
          proxy_set_header Authorization $http_authorization;
          proxy_set_header Cookie "";
          access_log off;
        '');
      };
      "^~ /oauth/" = auth "" ''limit_req zone=protected_api_per_ip burst=10 nodelay; limit_req_status 429;'';
      "= /.well-known/oauth-authorization-server" = auth "/.well-known/oauth-authorization-server" "";
      "= /.well-known/oauth-protected-resource" = auth "/.well-known/oauth-protected-resource" "";
      "= /.well-known/oauth-protected-resource/mcp" = auth "/.well-known/oauth-protected-resource/mcp" "";
    };
    services.nginx.virtualHosts."log.mrj.am".locations = lib.mkForce {
      "/" = {
        proxyPass = "https://127.0.0.1:8443";
        extraConfig = ''
          client_max_body_size 64k;
          proxy_set_header Host log.mrj.am;
          proxy_set_header X-Forwarded-For $remote_addr;
          proxy_ssl_server_name on;
          proxy_ssl_name log.mrj.am;
          proxy_ssl_verify on;
          proxy_ssl_verify_depth 2;
          proxy_ssl_trusted_certificate ${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt;
          proxy_set_header Connection "";
        '';
      };
      "= /ui/login/begin" = {
        proxyPass = socket;
        extraConfig = ''
          client_max_body_size 8k;
          access_log off;
          proxy_set_header X-Mrjam-Service "log-idp";
          proxy_set_header X-Forwarded-Host $host;
          proxy_set_header X-Forwarded-Proto $scheme;
          proxy_set_header Origin $http_origin;
          limit_req zone=protected_api_per_ip burst=5 nodelay;
          limit_req_status 429;
        '';
      };
      # Administration et import restent loopback, auto-service natif conservé.
      "^~ /v1/raw/".return = "404";
      "^~ /v1/oauth2/".return = "404";
      "^~ /v1/service_account/".return = "404";
      "^~ /scim/".return = "404";
      "^~ /realms/".return = "410";
    };
  }) ];
}
