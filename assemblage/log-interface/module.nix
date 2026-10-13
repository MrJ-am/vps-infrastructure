{ locations, site, paquetMetier }:
{ lib, ... }:
let
  securite = ''
    access_log off;
    error_log /dev/null emerg;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header Referrer-Policy "strict-origin" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Cache-Control "no-store" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; form-action 'self'" always;
  '';
  page = { root = site; tryFiles = "/index.html =404"; extraConfig = securite + ''
    error_page 418 = @mrjam_log_natif;
    if ($request_method !~ ^(GET|HEAD)$) { return 418; }
  ''; };
  fichier = { root = site; tryFiles = "$uri =404"; extraConfig = securite; };
in {
  infrastructure.metier.paquet = lib.mkForce paquetMetier;
  services.nginx.virtualHosts."log.mrj.am".locations = lib.mkOverride 30 (locations // {
    "= /" = page;
    "= /ui" = page;
    "^~ /ui/" = page;
    "^~ /ui/images/" = locations."/";
    "= /index.html" = page;
    "= /elm.js" = fichier;
    "= /pont.js" = fichier;
    "= /revision.json" = fichier;
    "^~ /assets/mrjam/" = fichier;
    "@mrjam_log_natif" = locations."/";
    "= /presentation/api" = {
      proxyPass = "http://unix:/run/mrjam-metier/http.sock:";
      extraConfig = ''
        client_max_body_size 64k;
        access_log off;
        error_log /dev/null emerg;
        proxy_set_header X-Mrjam-Service "log-idp";
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Origin $http_origin;
        proxy_set_header Authorization "";
        limit_req zone=protected_api_per_ip burst=20 nodelay;
        limit_req_status 429;
      '';
    };
  });
}
