{ lib, ... }:
let
  projects = builtins.fromJSON (builtins.readFile ../projects.json);
  sites = builtins.attrValues projects;
  domains = lib.concatMap (site: [ site.domain ] ++ site.aliases) sites;
  ports = map (site: site.port) sites;
  validDomain = name: builtins.isString name &&
    builtins.match "[a-z0-9]([a-z0-9.-]*[a-z0-9])?" name != null;
  validSite = site:
    builtins.isInt site.port && site.port >= 1024 && site.port <= 65535 &&
    builtins.isString site.prefix &&
    (site.prefix == "" || builtins.match "(/[a-zA-Z0-9_-]+)+" site.prefix != null) &&
    builtins.match "[1-9][0-9]*[km]" site.maxBodySize != null;

in {
  assertions = [
    { assertion = sites != []; message = "La passerelle doit conserver au moins un projet."; }
    { assertion = builtins.length domains == builtins.length (lib.unique domains);
      message = "Un domaine ou alias est attribué à plusieurs projets."; }
    { assertion = builtins.length ports == builtins.length (lib.unique ports);
      message = "Un port HTTP local est attribué à plusieurs projets."; }
    { assertion = lib.all validDomain domains && lib.all validSite sites;
      message = "Domaine, port, préfixe ou taille de requête invalide dans projects.json."; }
  ];
  security.acme.acceptTerms = true;
  services.nginx.enable = true;
  services.nginx.virtualHosts = (import ../lib/virtual-hosts.nix) projects;
  networking.firewall.allowedTCPPorts = [ 80 443 ];
}
