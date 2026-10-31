# Inert package for review, not a NixOS host or an activation instruction.
{ pkgs }:
let
  target = builtins.fromJSON (builtins.readFile ./mrjam-vps.json);
  publicKeyFile = ./keys/mrjam-inventory.pub;
in
assert target.source_authority == "MrJ-am/vps-infrastructure";
assert builtins.hashFile "sha256" publicKeyFile == target.inventory_adoption.public_key_file_sha256;
pkgs.callPackage ../inventory/package.nix {
  inherit (target.inventory_adoption) uid gid;
  publicKeys = [ (pkgs.lib.removeSuffix "\n" (builtins.readFile publicKeyFile)) ];
}
