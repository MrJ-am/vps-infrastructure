{ lib, ... }:
{
  imports = [ ./configuration.nix ];

  # Première activation seulement : permettre le challenge HTTP-01 avant
  # l'existence du certificat. La configuration finale impose HTTPS.
  services.nginx.virtualHosts."cloud.mrj.am".forceSSL = lib.mkForce false;
}
