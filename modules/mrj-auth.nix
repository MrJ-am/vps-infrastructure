{ config, lib, pkgs, ... }:
let
  projects = config.infrastructure.gateway.projects;
  sites = lib.filter (site: site ? browserAuth && site.browserAuth) (builtins.attrValues projects);
  oidc = config.infrastructure.visionMultiutilisateur.enable or false;
  python = pkgs.python3.withPackages (p: [ p.passlib ] ++ lib.optionals oidc [ p.authlib p.requests p.psycopg ]);
  source = pkgs.runCommand "mrj-auth-source" {} ''
    mkdir -p "$out"
    cp ${../services/mrj-auth/server.py} "$out/server.py"
    cp ${../services/mrj-auth/oauth.py} "$out/oauth.py"
    cp ${../services/mrj-auth/oidc.py} "$out/oidc.py"
    cp ${../services/mrj-auth/mcp.html} "$out/mcp.html"
    cp ${../services/mrj-auth/mcp.js} "$out/mcp.js"
    cp ${../services/mrj-auth/style.css} "$out/style.css"
  '';
  sessionHeaders = ''
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Authorization "";
  '';
  jsonError = code: error: {
    extraConfig = ''
      default_type application/json;
      add_header Cache-Control "no-store" always;
      add_header Strict-Transport-Security "max-age=31536000" always;
      add_header X-Content-Type-Options "nosniff" always;
      return ${toString code} '{"error":"${error}"}';
    '';
  };
in lib.mkIf (sites != []) {
  assertions = [ {
    assertion = lib.all (site: (site.domain == "mrj.am" || lib.hasSuffix ".mrj.am" site.domain) && site.port != 3002) sites
      && lib.all (site: (site.port or null) != 3002) (builtins.attrValues projects);
    message = "Les sessions mrj.am exigent un domaine mrj.am et réservent le port local 3002.";
  } ];
  users.groups.mrj-auth = {};
  users.users.mrj-auth = { isSystemUser = true; group = "mrj-auth"; extraGroups = [ "vision-auth" ]; };
  systemd.services.mrj-auth = {
    description = "Authentification commune aux sites mrj.am";
    wantedBy = [ "multi-user.target" ];
    after = [ "systemd-tmpfiles-setup.service" ];
    environment = {
      MRJ_AUTH_DATABASE = "/var/lib/mrj-auth/sessions.sqlite";
      MRJ_AUTH_CREDENTIALS = "/var/lib/vision/auth/htpasswd";
      MRJ_AUTH_DOMAIN = "mrj.am";
      MRJ_AUTH_HOSTS = lib.concatStringsSep "," (map (site: site.domain) sites);
    } // lib.optionalAttrs oidc {
      MRJ_AUTH_MODE = "oidc";
      MRJ_OIDC_ISSUER = "https://log.mrj.am/realms/mrjam";
      MRJ_OIDC_BACKEND = "http://127.0.0.1:8085/realms/mrjam";
      MRJ_OIDC_CLIENT = "mrjam-vision";
      MRJ_OIDC_SECRET_FILE = "/run/credentials/mrj-auth.service/oidc-client";
      MRJ_IDENTITES_DSN = "dbname=vision user=vision_identite host=/run/postgresql";
    };
    serviceConfig = {
      ExecStart = "${python}/bin/python3 ${source}/server.py";
      User = "mrj-auth"; Group = "mrj-auth";
      StateDirectory = "mrj-auth"; StateDirectoryMode = "0700";
      Restart = "on-failure"; RestartSec = 3; UMask = "0077";
      NoNewPrivileges = true; PrivateTmp = true; PrivateDevices = true;
      ProtectSystem = "strict"; ProtectHome = true;
      ProtectKernelTunables = true; ProtectKernelModules = true;
      ProtectControlGroups = true; RestrictSUIDSGID = true;
      CapabilityBoundingSet = ""; RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" ];
      IPAddressDeny = "any"; IPAddressAllow = [ "127.0.0.0/8" ];
      TasksMax = 32; MemoryMax = "192M";
      LoadCredential = lib.optionals oidc [ "oidc-client:${config.infrastructure.identite.secretClient}" ];
    };
  };
  services.nginx.virtualHosts = builtins.listToAttrs (map (site: {
    name = site.domain;
    value.locations = {
      "/auth/" = {
        proxyPass = "http://127.0.0.1:3002";
        extraConfig = sessionHeaders + ''
          access_log off;
          client_max_body_size 8k;
          limit_req zone=protected_api_per_ip burst=5 nodelay;
          limit_req_status 429;
          error_page 429 = @mrj-rate-limited;
        '';
      };
      "= /_mrj_session" = {
        proxyPass = "http://127.0.0.1:3002/verify";
        extraConfig = sessionHeaders + ''
          internal;
          proxy_pass_request_body off;
          proxy_set_header Content-Length "";
          proxy_set_header X-Original-Method $mrj_original_method;
          proxy_set_header X-CSRF-Token $http_x_csrf_token;
        '';
      };
      "/api/web/" = {
        proxyPass = "http://127.0.0.1:${toString site.port}";
        extraConfig = ''
          client_max_body_size ${site.maxBodySize};
          set $mrj_original_method $request_method;
          auth_request /_mrj_session;
          auth_request_set $mrj_user $upstream_http_x_mrj_user;
          proxy_set_header Host $host;
          proxy_set_header X-Forwarded-Proto $scheme;
          proxy_set_header X-Forwarded-For $remote_addr;
          proxy_set_header Authorization "";
          proxy_set_header Cookie "";
          proxy_set_header X-CSRF-Token "";
          proxy_set_header X-Vision-Authenticated "1";
          proxy_set_header X-Vision-Browser "1";
          proxy_set_header X-Mrj-User $mrj_user;
          limit_req zone=protected_api_per_ip burst=20 nodelay;
          limit_req_status 429;
          error_page 401 = @mrj-auth-required;
          error_page 403 = @mrj-csrf-required;
          error_page 429 = @mrj-rate-limited;
        '';
      };
      "@mrj-auth-required" = jsonError 401 "authentication_required";
      "@mrj-csrf-required" = jsonError 403 "csrf_required";
      "@mrj-rate-limited" = jsonError 429 "rate_limited";
    };
  }) sites);
}
