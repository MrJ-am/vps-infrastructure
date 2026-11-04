let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {};lib=pkgs.lib;
  baseline=import ./staging-host.nix;
  base=import ./acceptance-host.nix;
  preparation=builtins.storePath /nix/store/aij7vndm5yqsm98bh1n7bccb3gp2z0hn-mrjam-delivery-preparation-1;
  control=baseline.evaluation.packages // {
    preparation=builtins.unsafeDiscardStringContext (toString preparation);
  };
  modules=base.modules++[(import ./delivery-control-plane.nix {inherit control;})];
  evaluate=mods: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=mods;}).config;
  before=evaluate baseline.modules;after=evaluate modules;
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (n: before.systemd.units.${n}.text!=after.systemd.units.${n}.text) names;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/9vpbs7mxmz13k7mf4y7m20r6cvmn661y-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    unitsUnchanged=builtins.attrNames after.systemd.units==names;
    onlyPreparationChanged=changed==["mrjam-delivery-preparation.service"];
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    adoptedUnchanged=before.environment.etc."mrjam-delivery-adopted.json".source==after.environment.etc."mrjam-delivery-adopted.json".source;
    observerUnchanged=before.systemd.services.mrjam-delivery-preparation.serviceConfig.LoadCredential
      ==after.systemd.services.mrjam-delivery-preparation.serviceConfig.LoadCredential;
  };
  state=baseline.evaluation.state // {system=toString after.system.build.toplevel;control_plane=control;};
in {
  inherit modules;
  evaluation={inherit checks changed state;system=state.system;packages=control;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
