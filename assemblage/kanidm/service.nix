# Module préparatoire, non importé par la configuration active avant qualification.
# TLS acquis au démarrage : le store ne contient que les chemins des credentials.
{ tlsChainFile, tlsKeyFile }:
{ lib, pkgs, ... }:
{
  assertions = map (chemin: {
    assertion = builtins.isString chemin && lib.hasPrefix "/" chemin
      && !(lib.hasPrefix "/nix/store/" chemin)
      && !(lib.hasInfix "\n" chemin) && !(lib.hasInfix "\r" chemin);
    message = "Kanidm : le credential TLS doit provenir d'un fichier runtime hors store.";
  }) [ tlsChainFile tlsKeyFile ];

  services.kanidm = {
    package = import ./paquet.nix { inherit pkgs; };
    server.enable = true;
    server.settings = {
      domain = "log.mrj.am";
      origin = "https://log.mrj.am";
      bindaddress = "127.0.0.1:8443";
      ldapbindaddress = null;
      tls_chain = "/run/credentials/kanidm.service/tls-chain";
      tls_key = "/run/credentials/kanidm.service/tls-key";
      online_backup.versions = 7;
    };
    # CLI/serveur officiels ; aucune intégration PAM, Unix ou provisioning tiers.
    unix.enable = false;
    client.enable = false;
    provision.enable = false;
  };
  systemd.services.kanidm.serviceConfig = {
    LoadCredential = [ "tls-chain:${tlsChainFile}" "tls-key:${tlsKeyFile}" ];
    UMask = "0077";
  };
}
