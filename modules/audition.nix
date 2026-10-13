{ config, lib, pkgs, ... }:
let
  cfg = config.infrastructure.audition;
  upstream = "http://unix:/run/mrjam-metier/http.sock:";
  proxy = service: extra: {
    proxyPass = upstream;
    extraConfig = ''
      proxy_set_header X-Mrjam-Service "${service}";
      proxy_set_header X-Forwarded-Host "audition.mrj.am";
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_set_header X-Mrj-User "";
      proxy_set_header X-Vision-Authenticated "";
      proxy_set_header X-Vision-Administration "";
      proxy_set_header X-CSRF-Token $http_x_csrf_token;
      proxy_set_header Origin $http_origin;
      access_log off;
      client_max_body_size 64k;
      limit_req zone=protected_api_per_ip burst=10 nodelay;
      limit_req_status 429;
    '' + extra;
  };
in {
  options.infrastructure.audition = {
    enable = lib.mkEnableOption "Audition intégré au serveur commun après qualification centrale";
    site = lib.mkOption { type = lib.types.nullOr lib.types.path; default = null;
      description = "Artefact Elm exact déjà qualifié, aucune construction lors de l'activation."; };
    paquet = lib.mkOption { type = lib.types.nullOr lib.types.package; default = null;
      description = "Même binaire central qualifié, incluant Audition et la présentation Log existante."; };
    preconditions = lib.mkOption { type = lib.types.bool; default = false;
      description = "Préconditions centrales : backup/restauration/retour, OAuth et candidat exact qualifiés."; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [ { assertion = config.infrastructure.metier.enable && config.infrastructure.log.enable && cfg.site != null && cfg.paquet != null && cfg.preconditions;
      message = "Audition exige le monolithe/Log, un site qualifié et les préconditions centrales ; ne jamais activer un aperçu."; } ];
    # Aucun nouveau processus ni compte Unix. Le rôle SQL ne possède pas le
    # schéma et ne reçoit aucun privilège sur les données des autres produits.
    services.postgresql.identMap = lib.mkOrder 1650 "mrjam_metier mrjam-metier audition_app";
    # La présentation Log publiée impose déjà son paquet à priorité30. La
    # promotion Audition fournit explicitement son nouveau monolithe commun ;
    # elle conserve le site Log et ne rejoue aucune bascule d'identité.
    infrastructure.metier.paquet = lib.mkOverride 20 cfg.paquet;
    systemd.services.mrjam-metier.environment.AUDITION_DSN = "host=/run/postgresql dbname=vision user=audition_app options='-c statement_timeout=5000'";
    services.nginx.virtualHosts."audition.mrj.am" = {
      enableACME = true;
      forceSSL = true;
      root = toString cfg.site;
      extraConfig = ''
        error_log /dev/null emerg;
        add_header X-Content-Type-Options nosniff always;
        add_header Referrer-Policy no-referrer always;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'" always;
      '';
      locations = {
        "/" = { tryFiles = "$uri /index.html"; };
        "^~ /api/audition/" = proxy "audition" ''proxy_set_header Authorization "";'';
        "= /mcp" = proxy "audition" ''proxy_set_header Cookie ""; proxy_set_header Authorization $http_authorization;'';
        "^~ /auth/" = proxy "log" ''proxy_set_header Authorization "";'';
        "^~ /oauth/" = proxy "log" ''proxy_set_header Authorization "";'';
        "= /.well-known/oauth-authorization-server" = proxy "log" "";
        "= /.well-known/oauth-protected-resource" = proxy "log" "";
        "= /.well-known/oauth-protected-resource/mcp" = proxy "log" "";
      };
    };
    # Schéma audition inclus dans la base Vision déjà couverte par la sauvegarde
    # centrale chiffrée. Migration et premier administrateur restent explicites,
    # sans service de migration implicite ni données de démonstration.
  };
}
