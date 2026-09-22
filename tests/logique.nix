# Les deux phases sont évaluées avec les autres applications présentes.
let
  lib = import <nixpkgs/lib>;
  evaluer = fichier: (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ fichier ];
  }).config;
  avant = evaluer ../hosts/hostinger/configuration.nix;
  acme = evaluer ../hosts/hostinger/logique-acme.nix;
  apres = evaluer ../hosts/hostinger/logique.nix;
  domaine = "logique.echos.systems";
  stable = c: {
    services = map (nom: c.systemd.units."${nom}.service".text)
      [ "sshd" "postgresql" "postgresql-setup" "matheval" "vision"
        "vision-migrate" "mrj-auth" "postgresqlBackup-matheval" "postgresqlBackup-vision" ];
    reseau = lib.mapAttrs (_: fichier: toString fichier.source)
      (lib.filterAttrs (nom: _: lib.hasPrefix "systemd/network" nom) c.environment.etc);
    pareFeu = c.networking.firewall.allowedTCPPorts;
    bases = c.services.postgresqlBackup.databases;
    sudo = c.security.sudo.extraRules;
    cles = c.users.users.root.openssh.authorizedKeys.keys;
    # Nginx dérive ces deux chemins depuis ACME ; les options brutes sont indéfinies.
    sites = map (nom: builtins.removeAttrs c.services.nginx.virtualHosts.${nom}
      [ "sslCertificate" "sslCertificateKey" ])
      [ "principiipetit.io" "www.principiipetit.io" "vision.mrj.am" ];
  };
in
assert builtins.all (c: builtins.all (a: a.assertion) c.assertions) [ avant acme apres ];
assert stable avant == stable acme && stable avant == stable apres;
assert !(avant.services.nginx.virtualHosts ? ${domaine});
assert acme.services.nginx.virtualHosts.${domaine}.enableACME;
assert !acme.services.nginx.virtualHosts.${domaine}.forceSSL;
assert !acme.services.nginx.virtualHosts.${domaine}.addSSL;
assert !acme.services.nginx.virtualHosts.${domaine}.onlySSL;
assert acme.services.nginx.virtualHosts.${domaine}.locations."/".return == "404";
assert acme.services.nginx.virtualHosts.${domaine}.root == null;
assert apres.services.nginx.virtualHosts.${domaine}.forceSSL;
assert apres.services.nginx.virtualHosts.${domaine}.root == "/srv/logique/current";
assert apres.services.nginx.virtualHosts.${domaine}.locations."/".tryFiles == "$uri $uri/ =404";
assert apres.services.nginx.virtualHosts.${domaine}.locations."= /matheval".return == "302 /?accueil=1";
assert apres.services.nginx.virtualHosts.${domaine}.locations."^~ /matheval/".return == "302 /?accueil=1";
assert lib.hasInfix "ssl_reject_handshake on" apres.services.nginx.appendHttpConfig;
assert !(apres.systemd.services ? logique);
assert !(apres.infrastructure.postgresql.projects ? logique);
{
  amorcage = acme.system.build.toplevel.drvPath;
  publication = apres.system.build.toplevel.drvPath;
  servicesExistantsConserves = true;
}
