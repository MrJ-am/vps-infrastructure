{ lib, ... }:
let
  racine = "/srv/vision-interface/current";
  entetes = ''
    add_header Cache-Control "no-cache" always;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Content-Security-Policy "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'" always;
  '';
  fichier = chemin: {
    root = racine;
    tryFiles = "${chemin} =404";
    extraConfig = entetes;
  };
in {
  # Le serveur Lisp, les sessions et les données restent dans leurs routes.
  services.nginx.virtualHosts."vision.mrj.am".locations = {
    "= /" = fichier "/app.html";
    "= /app.js" = fichier "/app.js";
    "= /app.css" = fichier "/app.css";
    "= /interface-manifest.json" = fichier "/manifest.json";
    "^~ /assets/mrjam/" = fichier "$uri";
  };
}
