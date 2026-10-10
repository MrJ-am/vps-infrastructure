# Reproduire une passerelle qui ne déclarait pas les modules de l'identité.
{ config, lib, ... }@args:
let ancien = import ../../../modules/gateway.nix args;
in ancien // {
  imports = [ ../../../modules/mrj-auth.nix ../../../modules/journal-http.nix ];
  options = lib.recursiveUpdate ancien.options {
    infrastructure.visionMultiutilisateur.enable = lib.mkEnableOption "ancien mode inactif";
  };
}
