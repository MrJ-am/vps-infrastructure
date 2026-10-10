# Une autre déclaration de source, conservant le paquet et les registres.
{ config, lib, pkgs, ... }@args: import ../../../modules/postgresql.nix args
