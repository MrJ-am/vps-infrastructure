{ config, ... }:
let
  site = (builtins.fromJSON (builtins.readFile ../projects.json)).vision;
  mobileLiveTestUsername = "mobile-live";
  mobileLiveTestPasswordHash = "$6$M0bLive26$eKajMiudVvi4/NSD3YFmHxun73Wiv5rR750TUzt.dwrT5urrD07wQ4kP9VB8hrmDJogaGiH7mYnQC75GplKtL1";
  mobileLiveTestAuthFile = "/var/lib/vision/auth/mobile-live-test.htpasswd";
in {
  imports = [ ../vendor/vision/vision.nix ];
  assertions = [{
    assertion = site.port == 3001 && site.prefix == "" &&
      site.domain == "vision.mrj.am" && site.service == "vision" &&
      site.auth.prefix == "/api/" &&
      site.auth.basicUserFile == "/var/lib/vision/auth/htpasswd" &&
      site.privateHealthPath == "/healthz" &&
      config.infrastructure.postgresql.projects.vision.name == "vision";
    message = "Changement du contrat Vision : coordonner le module applicatif avant activation.";
  }];
  services.vision = {
    enable = true;
    domain = site.domain;
    port = site.port;
    version = "1.3.0";
    bootstrapSource = ../vendor/vision/source;
    bootstrapCommit = "151ab64bd5c9c5c54297e88dbe4d548343cc4928";
    deploymentPublicKeys = [];
    backupRecipient = "age15zfsttzkz0n553mgq07czxk98j65y6pg47563c7gvneq65dmfgjs3x0x0l";
  };

  # Ce condensat ne donne acces qu'a une reponse de test constante. Le mot de
  # passe jetable est transmis au proprietaire hors Git et sera supprime avec
  # cette route a la fin de l'essai Mobile Live.
  systemd.tmpfiles.rules = [
    "f+ ${mobileLiveTestAuthFile} 0640 root vision-auth - ${mobileLiveTestUsername}:${mobileLiveTestPasswordHash}"
  ];

  # Une correspondance exacte passe avant la protection generale de /api/.
  # Ainsi, les identifiants jetables ne fonctionnent sur aucune autre route.
  services.nginx.virtualHosts.${site.domain}.locations = {
    "= /mcp" = {
      proxyPass = "http://127.0.0.1:${toString site.port}";
      extraConfig = ''
        client_max_body_size 64k;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        satisfy any;
        auth_request /_vision_mcp_token;
        auth_basic "${site.auth.realm}";
        auth_basic_user_file ${site.auth.basicUserFile};
        limit_req zone=protected_api_per_ip burst=10 nodelay;
        limit_conn protected_api_connections 10;
        limit_req_status 429;
        limit_conn_status 429;
        proxy_set_header Authorization "";
        proxy_set_header X-Vision-Authenticated "1";
        proxy_set_header X-Vision-Browser "";
        proxy_set_header X-Mrj-User "";
        proxy_set_header Cookie "";
        error_page 401 = @vision-mcp-authentication-required;
        error_page 429 = @vision-rate-limited;
      '';
    };
    "= /_vision_mcp_token" = {
      proxyPass = "http://127.0.0.1:3002/verify-mcp";
      extraConfig = ''
        internal;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization $http_authorization;
        proxy_set_header Cookie "";
      '';
    };
    "= /.well-known/oauth-protected-resource" = {
      proxyPass = "http://127.0.0.1:3002";
      extraConfig = ''
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization "";
      '';
    };
    "= /.well-known/oauth-protected-resource/mcp" = {
      proxyPass = "http://127.0.0.1:3002";
      extraConfig = ''
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization "";
      '';
    };
    "= /.well-known/oauth-authorization-server" = {
      proxyPass = "http://127.0.0.1:3002";
      extraConfig = ''
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization "";
      '';
    };
    "^~ /oauth/" = {
      proxyPass = "http://127.0.0.1:3002";
      extraConfig = ''
        client_max_body_size 8k;
        limit_req zone=protected_api_per_ip burst=5 nodelay;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Authorization "";
      '';
    };
    "@vision-mcp-authentication-required" = {
      extraConfig = ''
        default_type application/json;
        add_header Cache-Control "no-store" always;
        add_header WWW-Authenticate 'Bearer realm="Vision MCP", resource_metadata="https://vision.mrj.am/.well-known/oauth-protected-resource/mcp"' always;
        add_header Strict-Transport-Security "max-age=31536000" always;
        return 401 '{"error":"authentication_required"}';
      '';
    };
    "= /api/v1/mobile-live-test" = {
      proxyPass = "http://127.0.0.1:${toString site.port}";
      extraConfig = ''
        client_max_body_size ${site.maxBodySize};
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        auth_basic "Vision Mobile Live test";
        auth_basic_user_file ${mobileLiveTestAuthFile};
        limit_req zone=protected_api_per_ip burst=3 nodelay;
        limit_conn protected_api_connections 2;
        limit_req_status 429;
        limit_conn_status 429;
        proxy_set_header Authorization "";
        proxy_set_header X-Vision-Authenticated "1";
        proxy_hide_header Cache-Control;
        proxy_hide_header X-Content-Type-Options;
        add_header Cache-Control "no-store" always;
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Robots-Tag "noindex, nofollow" always;
        error_page 401 = @vision-mobile-live-test-authentication-required;
        error_page 429 = @vision-rate-limited;
      '';
    };
    "@vision-mobile-live-test-authentication-required" = {
      extraConfig = ''
        default_type application/json;
        add_header Cache-Control "no-store" always;
        add_header WWW-Authenticate 'Basic realm="Vision Mobile Live test", charset="UTF-8"' always;
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Robots-Tag "noindex, nofollow" always;
        return 401 '{"error":"authentication_required","message":"Disposable HTTP Basic credentials are required for this test."}';
      '';
    };
  };
}
