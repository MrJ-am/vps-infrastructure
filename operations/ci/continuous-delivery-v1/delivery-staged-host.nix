# Build the inactive-slot configuration. This expression grants no activation.
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib=(import nixpkgs {}).lib;
  baseline=import ./admission-host.nix;
  qualification=import ./delivery-host-qualification.nix;
  server=import ./delivery-server-qualification.nix;
  runtime=import ./delivery-complete-runtime-qualification.nix;
  replacement=import ./slot-artifacts.nix {
    slot="green";
    serverStorePath=builtins.unsafeDiscardStringContext (toString server);
    runtimeStorePath=builtins.unsafeDiscardStringContext (toString runtime);
  };
  modules=baseline.modules++[replacement];
  config=(import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";inherit modules;}).config;
in {
  inherit modules;
  toplevel=assert lib.all (x: x) (builtins.attrValues qualification.checks);config.system.build.toplevel;
}
