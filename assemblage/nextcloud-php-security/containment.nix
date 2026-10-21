{ lib, ... }:
{
  # Réponse statique avant toute sélection de location ou exécution de PHP.
  services.nginx.virtualHosts."cloud.mrj.am".extraConfig = lib.mkBefore ''
    return 503;
  '';
}
