{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  eval = modules: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    inherit modules;
  }).config;
  original = eval [ ../hosts/mrjam-vps/candidate-promoted.nix ];
  proposed = eval [ ../hosts/mrjam-vps/candidate-promoted.nix ../hosts/mrjam-vps/resolver-unicast.nix ];
  unitNames = builtins.attrNames original.systemd.units;
  results = {
    validAssertions = lib.all (item: item.assertion) proposed.assertions;
    resolvedRemainsEnabled = original.services.resolved.enable && proposed.services.resolved.enable;
    onlyLlmnrSettingChanges = builtins.removeAttrs proposed.services.resolved.settings.Resolve [ "LLMNR" ]
      == original.services.resolved.settings.Resolve;
    llmnrDisabled = proposed.services.resolved.settings.Resolve.LLMNR == false;
    dnsStubNotDisabled = !(proposed.services.resolved.settings.Resolve ? DNSStubListener);
    networkConfigurationPreserved = lib.all (field:
      original.systemd.network.networks."05-matheval-eth0".${field}
      == proposed.systemd.network.networks."05-matheval-eth0".${field})
      [ "matchConfig" "networkConfig" "address" "dns" "domains" "routes" ];
    firewallUnchanged = original.networking.firewall.allowedTCPPorts == proposed.networking.firewall.allowedTCPPorts
      && original.networking.firewall.allowedUDPPorts == proposed.networking.firewall.allowedUDPPorts;
    noUnitAddedOrRemoved = unitNames == builtins.attrNames proposed.systemd.units;
    allOtherUnitBytesUnchanged = lib.all (name: name == "systemd-resolved.service"
      || original.systemd.units.${name}.text == proposed.systemd.units.${name}.text) unitNames;
  };
in assert lib.all (value: value) (builtins.attrValues results); results
