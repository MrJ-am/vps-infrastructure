let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {};lib=pkgs.lib;
  previous=import ./admission-controller-host.nix;
  addition=[{
    # /etc activation replaces the regular policy file atomically. A bind of
    # that inode becomes unlinked (nlink=0) inside the retained runner. Bind
    # its root-owned directory read-only so each task opens the current file.
    systemd.services.mrjam-forgejo-runner.serviceConfig.BindReadOnlyPaths=lib.mkForce [
      "/run/mrjam-validation-collector/request.sock"
      "/etc/mrjam-forgejo-runner"
    ];
  }];
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux";modules=previous.modules++extra;
  }).config;
  before=evaluate [];after=evaluate addition;
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/6yalib0qwm5yjrzhc1yrmnjdpjip8aqb-nixos-system-srv1982677-26.05pre-git";
    onlyRunnerChanged=changed==["mrjam-forgejo-runner.service"];
    unitsUnchanged=names==builtins.attrNames after.systemd.units;
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    policyUnchanged=before.environment.etc."mrjam-forgejo-runner/admission.json"==after.environment.etc."mrjam-forgejo-runner/admission.json";
    runnerUnchanged=before.systemd.services.mrjam-forgejo-runner.serviceConfig.ExecStart==after.systemd.services.mrjam-forgejo-runner.serviceConfig.ExecStart;
  };
in {
  modules=previous.modules++addition;
  evaluation={inherit checks changed;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
