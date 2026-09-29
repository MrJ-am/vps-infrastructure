let
  lib = import <nixpkgs/lib>;
  config = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ ../hosts/hostinger/nextcloud-acme.nix ];
  }).config;
  hote = config.services.nginx.virtualHosts."cloud.mrj.am";
in
assert builtins.all (assertion: assertion.assertion) config.assertions;
assert !config.services.nextcloud.enable;
assert hote.enableACME;
assert !hote.forceSSL;
assert hote.locations."/".return == "503";
assert config.infrastructure.logique.phase == "https";
assert config.services.nginx.virtualHosts ? "logique.echos.systems";
assert config.services.nginx.virtualHosts ? "vision.mrj.am";
assert config.services.nginx.virtualHosts ? "principiipetit.io";
true
