{ lib, ... }:
{
  # Conserver le site Logique et tous les services de l'entrée de production.
  imports = [ ./logique.nix ];

  # Candidat d'amorçage uniquement, à construire et vérifier avant activation.
  # Le déploiement doit réserver HTTP au challenge ACME jusqu'à HTTPS valide.
  services.nginx.virtualHosts."cloud.mrj.am".forceSSL = lib.mkForce false;
  services.nextcloud.https = lib.mkForce false;
}
