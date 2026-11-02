# Build only the inactive helper and generated unit, never a system activation.
{ nixpkgs }:
let
  pkgs=import nixpkgs {system="x86_64-linux";};
  package=pkgs.callPackage ./package.nix {};
  system=import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux";
    modules=[./unit.nix ({...}:{
      system.stateVersion="26.05";
      services.mrjamPasskeyNginxRoute={enable=true;inherit package;};
    })];
  };
in {inherit package;unit=system.config.systemd.units."mrjam-passkey-nginx-route.service".unit;}
