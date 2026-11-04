let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {};lib=pkgs.lib;
  previous=import ./intake-prepare-host.nix;
  baseline=previous.modules++[{services.mrjamIntakePreparation.package=lib.mkOverride 40
    (builtins.appendContext "/nix/store/vs5dc3klynsc1xm83sm9l55s4aqrz60f-mrjam-exact-intake-preparation-1" {
      "/nix/store/s4sy5d8p81a0kvgz2cqf4pl56qmmiwm1-mrjam-exact-intake-preparation-1.drv"={outputs=["out"];};
    });}];
  addition=[./admission-controller-module.nix {
    services.mrjamAdmissionController.enable=true;
    services.mrjamIntakePreparation.package=lib.mkOverride 30 (import ./intake-prepare.nix {inherit pkgs;});
  }];
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=baseline++extra;}).config;
  before=evaluate [];after=evaluate addition;
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  added=lib.subtractLists names (builtins.attrNames after.systemd.units);
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/qjkig4qypn3640v2i9gb1qi4w0r48hj6-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyPreparationAndTmpfilesChanged=changed==["mrjam-intake-prepare.service" "systemd-tmpfiles-resetup.service"];
    onlyDecisionDirectoryAdded=lib.subtractLists before.systemd.tmpfiles.rules after.systemd.tmpfiles.rules
      ==["d /var/lib/mrjam-intake-decisions 0755 root root -"]
      && lib.subtractLists after.systemd.tmpfiles.rules before.systemd.tmpfiles.rules==[];
    tmpfilesCommandUnchanged=before.systemd.services.systemd-tmpfiles-resetup.serviceConfig
      ==after.systemd.services.systemd-tmpfiles-resetup.serviceConfig;
    onlyControllerAdded=added==["mrjam-admission-controller.service" "mrjam-admission-controller.timer"];
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    greenRemainsActive=after.mrjamVpsApplications.activeSlot=="green";
    authorityUnchanged=before.services.mrjamValidationAuthority.package==after.services.mrjamValidationAuthority.package;
    discoveryUnchanged=before.services.mrjamGithubDiscovery.package==after.services.mrjamGithubDiscovery.package;
    signingKeyInaccessible=builtins.elem "-/var/lib/mrjam-validation-authority/signing-key" after.systemd.services.mrjam-admission-controller.serviceConfig.InaccessiblePaths;
    boundedPreparation=after.systemd.services.mrjam-intake-prepare.serviceConfig.TemporaryFileSystem==["/tmp:rw,size=512M,mode=1777"];
  };
in {
  modules=baseline++addition;
  evaluation={inherit checks changed added;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
