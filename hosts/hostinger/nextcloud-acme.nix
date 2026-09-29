{ lib, ... }:
{
  # Conserver le site Logique et tous les services de l'entrée de production.
  imports = [ ./logique.nix ];

  # Candidat d'amorçage uniquement, à construire et vérifier avant activation.
  # Le déploiement doit réserver HTTP au challenge ACME jusqu'à HTTPS valide.
  services.nextcloud.enable = lib.mkForce false;
  # Le registre PostgreSQL impose ce compte même avant l'activation de l'app.
  users.groups.nextcloud = {};
  users.users.nextcloud = { isSystemUser = true; group = "nextcloud"; };
  services.nginx.virtualHosts."cloud.mrj.am" = {
    forceSSL = lib.mkForce false;
    # Le challenge ACME est inséré par le module Nginx dans sa location dédiée.
    # Toute autre requête HTTP reçoit 503 : aucun formulaire ni cookie en clair.
    locations."/".return = "503";
  };
}
