{ pkgs, tlsKeyFile ? "/var/lib/fixture-kanidm/tls-key.pem" }:
let
  eval = import (pkgs.path + "/nixos/lib/eval-config.nix") {
    inherit pkgs;
    system = "x86_64-linux";
    modules = [
      (import ../assemblage/kanidm/service.nix {
        tlsChainFile = "/var/lib/fixture-kanidm/tls-chain.pem";
        inherit tlsKeyFile;
      })
      { boot.isContainer = true; system.stateVersion = "26.05"; }
    ];
  };
  c = eval.config;
  s = c.systemd.services.kanidm.serviceConfig;
in assert c.services.kanidm.package.version == "1.11.2";
assert !c.services.kanidm.package.enableSecretProvisioning;
assert !c.services.kanidm.provision.enable;
assert !c.services.kanidm.unix.enable;
assert c.services.kanidm.server.settings.origin == "https://log.mrj.am";
assert c.services.kanidm.server.settings.domain == "log.mrj.am";
assert c.services.kanidm.server.settings.bindaddress == "127.0.0.1:8443";
assert c.services.kanidm.server.settings.ldapbindaddress == null;
assert s.User == "kanidm" && s.Group == "kanidm";
assert s.StateDirectoryMode == "0700";
assert s.UMask == "0077";
assert s.LoadCredential == [
  "tls-chain:/var/lib/fixture-kanidm/tls-chain.pem"
  "tls-key:${tlsKeyFile}"
];
assert builtins.all (a: a.assertion) c.assertions;
{
  version = c.services.kanidm.package.version;
  user = s.User;
  stateMode = s.StateDirectoryMode;
  secretsDansStore = false;
  provisioning = c.services.kanidm.provision.enable;
  unix = c.services.kanidm.unix.enable;
  ldap = c.services.kanidm.server.settings.ldapbindaddress;
  cible = "configuration évaluée ; aucun serveur installé/démarré";
}
