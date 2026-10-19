{ configuration, correction }:
let
  pkgs = import <nixpkgs> { system = "x86_64-linux"; };
  lib = pkgs.lib;
  eval = modules: (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; inherit modules;
  }).config;
  b = eval [ (builtins.toPath configuration) ];
  c = eval [ (builtins.toPath configuration) (builtins.toPath correction) ];
  units = cfg: lib.mapAttrs (_: u: u.text) cfg.systemd.units;
  protected = cfg: {
    units = builtins.removeAttrs (units cfg) [ "mrjam-metier.service" ];
    metier = cfg.systemd.services.mrjam-metier.serviceConfig;
    metierUnit = builtins.filter (line: !(lib.hasInfix "VISION_PUBLIC_MCP_URL=" line))
      (lib.splitString "\n" cfg.systemd.units."mrjam-metier.service".text);
    environment = builtins.removeAttrs cfg.systemd.services.mrjam-metier.environment
      [ "VISION_PUBLIC_MCP_URL" ];
    package = toString cfg.infrastructure.metier.paquet;
    kernel = toString cfg.boot.kernelPackages.kernel;
    ports = cfg.networking.firewall.allowedTCPPorts;
    packages = map toString cfg.environment.systemPackages;
  };
in {
  before = toString b.system.build.toplevel;
  after = toString c.system.build.toplevel;
  invariants = protected b == protected c;
  assertions = builtins.all (a: a.assertion) c.assertions;
  urlBefore = b.systemd.services.mrjam-metier.environment.VISION_PUBLIC_MCP_URL or null;
  urlAfter = c.systemd.services.mrjam-metier.environment.VISION_PUBLIC_MCP_URL;
  executable = c.systemd.services.mrjam-metier.serviceConfig.ExecStart;
  changedUnits = builtins.filter (n: ((units b).${n} or null) != ((units c).${n} or null))
    (lib.unique (builtins.attrNames (units b) ++ builtins.attrNames (units c)));
}
