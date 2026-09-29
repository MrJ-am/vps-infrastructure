{ lib, ... }:
{
  imports = [ ./configuration.nix ];

  # Première activation seulement : permettre le challenge HTTP-01 avant
  # l'existence du certificat. Aucun compte n'existe encore.
  services.nginx.virtualHosts."cloud.mrj.am".forceSSL = lib.mkForce false;
  services.nextcloud.https = lib.mkForce false;
}
