{ config, lib, ... }:
let
  site = builtins.fromJSON (builtins.readFile ../operations/logique-site.json);
in {
  options.infrastructure.logique.phase = lib.mkOption {
    type = lib.types.enum [ "acme" "https" ];
    default = "acme";
    description = "ACME seul, puis publication HTTPS lors de la bascule coordonnée.";
  };
  config = {
    infrastructure.gateway.projects = lib.mkForce (
      (builtins.fromJSON (builtins.readFile ../projects.json)) // { logique = site; }
    );
    # L'amorçage ne sert aucun fichier applicatif, et n'exige pas encore de TLS.
    services.nginx.virtualHosts.${site.domain} = lib.mkIf
      (config.infrastructure.logique.phase == "acme") (lib.mkForce {
        enableACME = true;
        forceSSL = false;
        addSSL = false;
        onlySSL = false;
        locations."/".return = "404";
      });
    systemd.tmpfiles.rules = [
      "d /srv/logique 0755 root root -"
      "d /srv/logique/releases 0755 root root -"
    ];
  };
}
