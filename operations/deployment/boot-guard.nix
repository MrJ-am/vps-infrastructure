{ pkgs, ... }:
let
  source = import ./boot-guard-package.nix { inherit pkgs; };
in {
  systemd.generators.mrjam-first-cutover-guard = "${source}/bin/mrjam-first-cutover-guard";
}
