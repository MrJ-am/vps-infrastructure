{ lib, ... }:
{
  # Conserver le site Logique et tous les services de l'entrée de production.
  imports = [ ./logique.nix ];

  # Candidat d'amorçage uniquement, à construire et vérifier avant activation.
  # Le déploiement doit réserver HTTP au challenge ACME jusqu'à HTTPS valide.
  services.nextcloud.enable = lib.mkForce false;
  services.nginx.virtualHosts."cloud.mrj.am" = {
    forceSSL = lib.mkForce false;
    # Le challenge ACME est inséré par le module Nginx dans sa location dédiée.
    # Toute autre requête HTTP reçoit 503 : aucun formulaire ni cookie en clair.
    locations."/".return = "503";
  };
}
