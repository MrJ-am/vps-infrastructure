{ config, lib, pkgs, ... }:
let
 cfg = config.infrastructure.visionCycle;
 python = pkgs.python3.withPackages (p: [ p.psycopg p.requests ]);
 source = pkgs.runCommand "vision-cycle-source" {} ''
   mkdir -p "$out"
   cp ${../services/vision-cycle/cycle.py} "$out/cycle.py"
   cp ${../services/mrjam-courriel/courriel.py} "$out/courriel.py"
 '';
in {
 options.infrastructure.visionCycle = {
   enable = lib.mkEnableOption "préavis et effacements Vision avec copie chiffrée externe";
   configPrivee = lib.mkOption { type = lib.types.str; default = "/var/lib/mrjam-identite/cycle.json"; };
   secretClient = lib.mkOption { type = lib.types.str; default = "/var/lib/mrjam-identite/cycle-client.secret"; };
 };
 config = lib.mkIf cfg.enable {
   assertions = [{ assertion = config.infrastructure.visionMultiutilisateur.enable && config.infrastructure.courriel.enable;
     message = "Le cycle de vie exige migrations/ACL Vision, identité et SMTP privé configurés."; }];
   users.groups.vision_cycle = {};
   users.users.vision_cycle = { isSystemUser = true; group = "vision_cycle"; };
   systemd.services.vision-cycle = {
     description = "Préavis et effacements Vision sans accès aux contenus";
     wantedBy = [ "multi-user.target" ]; after = [ "postgresql.service" "keycloak.service" ];
     environment = {
       VISION_CYCLE_DSN = "dbname=vision user=vision_cycle host=/run/postgresql";
       MRJ_SMTP_SECRET = "/run/credentials/vision-cycle.service/smtp";
       VISION_CYCLE_CONFIG = "/run/credentials/vision-cycle.service/config";
       VISION_CYCLE_CLIENT_SECRET = "/run/credentials/vision-cycle.service/client";
       AGE = "${pkgs.age}/bin/age";
     };
     serviceConfig = {
       ExecStart = "${python}/bin/python3 ${source}/cycle.py";
       User = "vision_cycle"; Group = "vision_cycle";
       StateDirectory = "vision-cycle"; StateDirectoryMode = "0700";
       LoadCredential = [ "smtp:${config.infrastructure.courriel.secret}" "config:${cfg.configPrivee}" "client:${cfg.secretClient}" ];
       Restart = "on-failure"; RestartSec = 5; UMask = "0077";
       NoNewPrivileges = true; PrivateTmp = true; PrivateDevices = true;
       ProtectSystem = "strict"; ProtectHome = true;
       ProtectKernelTunables = true; ProtectKernelModules = true;
       ProtectControlGroups = true; RestrictSUIDSGID = true; CapabilityBoundingSet = "";
       RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
       MemoryMax = "192M"; TasksMax = 32;
     };
   };
   services.nginx.virtualHosts."vision.mrj.am".locations."= /api/web/effacer_compte" = {
     proxyPass = "http://127.0.0.1:3026";
     extraConfig = ''
       set $mrj_original_method $request_method;
       auth_request /_mrj_session;
       auth_request_set $mrj_user $upstream_http_x_mrj_user;
       proxy_set_header X-Vision-Authenticated "1";
       proxy_set_header X-Vision-Browser "1";
       proxy_set_header X-Mrj-User $mrj_user;
       proxy_set_header Authorization "";
       proxy_set_header Cookie "";
       client_max_body_size 1k;
       limit_req zone=protected_api_per_ip burst=5 nodelay;
       error_page 401 = @mrj-auth-required;
       error_page 403 = @mrj-csrf-required;
     '';
   };
 };
}
