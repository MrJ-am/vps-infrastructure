# The host keeps its iptables-nft INPUT firewall while CI adds one independent
# nftables OUTPUT table. NixOS suppresses the old NAT cleanup as soon as nftables
# is enabled, even with NAT disabled. Reuse that exact host-module cleanup rather
# than silently changing firewall.service or copying its shell implementation.
{ config, lib, pkgs, modulesPath, ... }:
let
  legacyNat = import (modulesPath + "/services/networking/nat-iptables.nix") {
    inherit lib pkgs;
    config = config // {
      networking = config.networking // {
        nftables = config.networking.nftables // { enable = false; };
      };
    };
  };
in {
  config = lib.mkMerge [
    {
      assertions = [ {
        assertion = !config.networking.nat.enable;
        message = "The CI coexistence profile requires the deployed NAT-disabled host.";
      } ];
      networking.nftables = { enable = true; flushRuleset = false; };
      networking.firewall = { backend = "iptables"; package = pkgs.iptables; };
    }
    # Do not redeclare the upstream options. With NAT disabled this configuration
    # contributes only the original mkBefore firewall.extraCommands cleanup.
    legacyNat.config
  ];
}
