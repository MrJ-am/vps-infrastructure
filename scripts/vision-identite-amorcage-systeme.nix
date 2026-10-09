{ configuration }:
let c = (import <nixpkgs/nixos/lib/eval-config.nix> {
  system = "x86_64-linux";
  modules = [ (builtins.toPath configuration) ];
}).config;
in toString c.system.build.toplevel
