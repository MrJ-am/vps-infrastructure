{ config, lib, pkgs, ... }:
let
 cfg = config.infrastructure.visionMultiutilisateur;
 python = pkgs.python3.withPackages (p: [ p.psycopg ]);
in {
 options.infrastructure.visionMultiutilisateur.enable = lib.mkEnableOption
   "isolation et administration Vision après les migrations 19 à 24";
 config = lib.mkIf cfg.enable {
   assertions = [{ assertion = config.infrastructure.identite.enable;
     message = "L'administration Vision exige l'identité OIDC et sa double authentification."; }];
   users.groups.vision_administration = {};
   users.users.vision_administration = { isSystemUser = true; group = "vision_administration"; };
   systemd.tmpfiles.rules = [ "d /var/lib/vision-effacements 0700 vision vision -" ];
   systemd.services.vision = {
     environment.VISION_REGISTRE_EFFACEMENTS = "/var/lib/vision-effacements/demandes.jsonl";
     serviceConfig.ReadWritePaths = [ "/var/lib/vision-effacements" ];
   };
   systemd.services.vision-gestion = {
     description = "Gestion Vision : droits, quotas, invitations, sans contenu";
     after = [ "postgresql.service" "mrj-auth.service" ];
     requires = [ "postgresql.service" ]; wantedBy = [ "multi-user.target" ];
     environment.VISION_GESTION_DSN = "dbname=vision user=vision_administration host=/run/postgresql";
     serviceConfig = {
       ExecStart = "${python}/bin/python3 ${../services/vision-gestion/server.py}";
       User = "vision_administration"; Group = "vision_administration";
       Restart = "on-failure"; UMask = "0077"; NoNewPrivileges = true;
       PrivateTmp = true; PrivateDevices = true; ProtectSystem = "strict"; ProtectHome = true;
       ProtectKernelTunables = true; ProtectKernelModules = true; ProtectControlGroups = true;
       RestrictSUIDSGID = true; CapabilityBoundingSet = "";
       RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" ];
       IPAddressDeny = "any"; IPAddressAllow = [ "127.0.0.0/8" ];
       TasksMax = 32; MemoryMax = "192M";
     };
   };
   systemd.services.vision-purge = {
     description = "Purge des données temporaires Vision sans export";
     after = [ "postgresql.service" ];
     serviceConfig = { Type = "oneshot"; User = "postgres"; UMask = "0077";
       ExecStart = "${config.services.postgresql.package}/bin/psql -X --set=ON_ERROR_STOP=1 --dbname=vision --command 'SELECT vision_gestion.purger(); SELECT vision_gestion.purger_admissions();'";
       NoNewPrivileges = true; ProtectSystem = "strict"; ProtectHome = true;
       PrivateTmp = true; RestrictAddressFamilies = [ "AF_UNIX" ]; };
   };
   systemd.timers.vision-purge = { wantedBy = [ "timers.target" ];
     timerConfig = { OnCalendar = "daily"; Persistent = true; RandomizedDelaySec = "10m"; }; };
   # Le compte HTTP n'exécute plus de DDL. La migration est effectuée par le
   # workflow d'exploitation, puis ce contrôle fixe du store valide son état.
   # Ne jamais exécuter en root un script d'une release du compte déployeur.
   systemd.services.vision-migrate.serviceConfig.ExecStart = lib.mkForce
     (pkgs.writeShellScript "vision-verifier-migrations" ''
       set -eu
       resultat=$(${config.services.postgresql.package}/bin/psql -XAt --set=ON_ERROR_STOP=1 \
         --command='SELECT count(*)=6 FROM vision_schema_migrations WHERE version BETWEEN 19 AND 24;')
       test "$resultat" = t
     '');
   services.nginx.virtualHosts."vision.mrj.am".locations = {
     "= /_vision_administration" = {
       proxyPass = "http://127.0.0.1:3002/verify-gestion";
       extraConfig = ''
         internal;
         proxy_pass_request_body off;
         proxy_set_header Content-Length "";
         proxy_set_header X-Forwarded-Host $host;
         proxy_set_header X-Forwarded-Proto $scheme;
         proxy_set_header X-Original-Method $vision_gestion_method;
         proxy_set_header X-CSRF-Token $http_x_csrf_token;
         proxy_set_header Origin $http_origin;
         proxy_set_header Authorization "";
       '';
     };
     "/api/gestion/" = {
       proxyPass = "http://127.0.0.1:3024";
       extraConfig = ''
         set $vision_gestion_method $request_method;
         auth_request /_vision_administration;
         auth_request_set $vision_gestion_user $upstream_http_x_mrj_user;
         proxy_set_header X-Vision-Administration "1";
         proxy_set_header X-Mrj-User $vision_gestion_user;
         proxy_set_header Authorization "";
         proxy_set_header Cookie "";
         client_max_body_size 8k;
         limit_req zone=protected_api_per_ip burst=5 nodelay;
         limit_req_status 429;
         error_page 401 = @mrj-auth-required;
         error_page 403 = @vision-verification-requise;
       '';
     };
     "@vision-verification-requise".extraConfig = ''
       default_type application/json;
       add_header Cache-Control "no-store" always;
       return 403 '{"erreur":"verification_renforcee_requise"}';
     '';
   };
 };
}
