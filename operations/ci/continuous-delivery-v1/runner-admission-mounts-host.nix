let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {};lib=pkgs.lib;
  previous=import ./validation-feedback-host.nix;
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux";modules=previous.modules++extra;
  }).config;
  before=evaluate [];
  required=["/var/lib/mrjam-validation-admissions" "/run/mrjam-validation-authority/request.sock"];
  original=before.systemd.services.mrjam-forgejo-runner.serviceConfig.BindReadOnlyPaths;
  addition=[{systemd.services.mrjam-forgejo-runner.serviceConfig.BindReadOnlyPaths=
    lib.mkOverride 40 (lib.unique (original++required));}];
  after=evaluate addition;
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/rks6y23zykcka5ifmilxj0p8r6nvrd57-nixos-system-srv1982677-26.05pre-git";
    onlyRunnerChanged=changed==["mrjam-forgejo-runner.service"];
    unitsUnchanged=names==builtins.attrNames after.systemd.units;
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    allOriginalMountsKept=lib.all (p: builtins.elem p after.systemd.services.mrjam-forgejo-runner.serviceConfig.BindReadOnlyPaths) original;
    onlyRequiredMountsAdded=lib.subtractLists original after.systemd.services.mrjam-forgejo-runner.serviceConfig.BindReadOnlyPaths==required;
    policyDirectoryRetained=builtins.elem "/etc/mrjam-forgejo-runner" original;
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    authorityUnchanged=before.services.mrjamValidationAuthority.package==after.services.mrjamValidationAuthority.package;
    rootUnchanged=before.systemd.services.mrjam-forgejo-runner.serviceConfig.RootDirectory==after.systemd.services.mrjam-forgejo-runner.serviceConfig.RootDirectory;
  };
in {
  modules=previous.modules++addition;
  evaluation={inherit checks changed;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
