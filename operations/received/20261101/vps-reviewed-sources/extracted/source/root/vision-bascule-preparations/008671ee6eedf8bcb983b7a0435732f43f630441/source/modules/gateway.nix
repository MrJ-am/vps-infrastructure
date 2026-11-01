{ config, lib, ... }:
let
  projects = config.infrastructure.gateway.projects;
  sites = builtins.attrValues projects;
  statique = site: (site.type or "proxy") == "static";
  natif = site: (site.type or "proxy") == "native";
  domains = lib.concatMap (site: [ site.domain ] ++ site.aliases) sites;
  ports = map (site: site.port) (lib.filter (site: !(statique site) && !(natif site)) sites);
  validDomain = name: builtins.isString name &&
    builtins.match "[a-z0-9]([a-z0-9.-]*[a-z0-9])?" name != null;
  validPath = path: builtins.isString path &&
    builtins.match "/[a-zA-Z0-9_./-]*" path != null &&
    !(lib.hasInfix ".." path) && !(lib.hasInfix "//" path);
  validAuth = site: !(site ? auth) ||
    builtins.attrNames site.auth == [ "basicUserFile" "prefix" "realm" ] &&
    validPath site.auth.prefix && lib.hasSuffix "/" site.auth.prefix &&
    lib.hasPrefix (site.prefix + "/") site.auth.prefix &&
    builtins.match "/var/lib/([a-zA-Z0-9_.-]+/)*[a-zA-Z0-9_.-]+" site.auth.basicUserFile != null &&
    !(lib.hasInfix ".." site.auth.basicUserFile) &&
    builtins.match "[a-zA-Z0-9 ._-]+" site.auth.realm != null &&
    site ? privateHealthPath && validPath site.privateHealthPath &&
    !(lib.hasPrefix site.auth.prefix site.privateHealthPath);
  validSite = site:
    (!(site ? browserAuth) || builtins.isBool site.browserAuth) &&
    (if statique site then
      !(site ? port) && !(site ? service) && !(site ? auth) && !(site ? browserAuth) &&
      !(site ? privateHealthPath) && site.prefix == "" &&
      builtins.match "/srv/[a-z][a-z0-9-]*/current" site.root != null
    else if natif site then
      !(site ? port) && !(site ? service) && !(site ? root) &&
      !(site ? auth) && !(site ? browserAuth) && !(site ? privateHealthPath) &&
      site.prefix == ""
    else (site.type or "proxy") == "proxy" && !(site ? root) &&
      builtins.isInt site.port && site.port >= 1024 && site.port <= 65535) &&
    builtins.isString site.prefix &&
    (site.prefix == "" || builtins.match "(/[a-zA-Z0-9_-]+)+" site.prefix != null) &&
    builtins.match "[1-9][0-9]*[km]" site.maxBodySize != null &&
    ((site ? auth) == (site ? privateHealthPath)) && validAuth site;
  hasProtectedAPI = lib.any (site: site ? auth) sites;

in {
  imports = [ ./mrj-auth.nix ./journal-http.nix ./identite.nix ./vision-gestion.nix ./courriel.nix ./vision-cycle.nix ./admission.nix ./fermeture.nix ];
  options.infrastructure.gateway.projects = lib.mkOption {
    type = lib.types.attrs;
    default = builtins.fromJSON (builtins.readFile ../projects.json);
    description = "Registre explicite du candidat ; aucun chargement distant.";
  };
  config = {
  assertions = [
    { assertion = sites != []; message = "La passerelle doit conserver au moins un projet."; }
    { assertion = builtins.length domains == builtins.length (lib.unique domains);
      message = "Un domaine ou alias est attribué à plusieurs projets."; }
    { assertion = builtins.length ports == builtins.length (lib.unique ports);
      message = "Un port HTTP local est attribué à plusieurs projets."; }
    { assertion = lib.all validDomain domains && lib.all validSite sites;
      message = "Domaine, port, préfixe, authentification ou taille de requête invalide dans projects.json."; }
  ];
  security.acme.acceptTerms = true;
  services.nginx = {
    enable = true;
    serverTokens = false;
    commonHttpConfig = lib.optionalString hasProtectedAPI ''
      limit_req_zone $binary_remote_addr zone=protected_api_per_ip:10m rate=5r/s;
      limit_conn_zone $binary_remote_addr zone=protected_api_connections:10m;
    '';
    virtualHosts = (import ../lib/virtual-hosts.nix)
      (lib.mapAttrs (id: site: site // lib.optionalAttrs
        (config.infrastructure.visionMultiutilisateur.enable && id=="vision") { oidcAuth = true; }) projects);
    # Un domaine oublié ne doit jamais emprunter le site ou le certificat d'un autre.
    appendHttpConfig = ''
      server {
        listen 80 default_server;
        listen [::]:80 default_server;
        server_name _;
        return 421;
      }
      server {
        listen 443 ssl default_server;
        listen [::]:443 ssl default_server;
        server_name _;
        ssl_reject_handshake on;
        return 421;
      }
    '';
  };
  networking.firewall.allowedTCPPorts = [ 80 443 ];
  };
}

