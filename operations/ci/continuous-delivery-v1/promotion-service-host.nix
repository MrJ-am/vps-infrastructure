let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib=(import nixpkgs {}).lib;
  baseline=import ./promotion-guard-host.nix;
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=baseline.modules++extra;}).config;
  installed=builtins.appendContext "/nix/store/59iq81v4s53h92f1h3xgq5lycywdxa2y-mrjam-protected-promotion-service-1" {
    "/nix/store/j3hp695kbdc40w9xipcg58x0nqiahxja-mrjam-protected-promotion-service-1.drv"={outputs=["out"];};
  };
  addition=[./promotion-service-module.nix {
    systemd.services.mrjam-promotion.serviceConfig.ExecStart=lib.mkOverride 20 "${installed}/bin/mrjam-promotion";
  }];before=evaluate [];after=evaluate addition;
  names=builtins.attrNames before.systemd.units;
  added=lib.subtractLists names (builtins.attrNames after.systemd.units);
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/scabzaalqsmnsvxcpfy54ygbzrpzq187-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyPromotionUnitsAdded=added==["mrjam-promotion.service" "mrjam-promotion.timer"];
    existingUnitsUnchanged=changed==[];
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    adoptedUnchanged=before.environment.etc."mrjam-delivery-adopted.json".source==after.environment.etc."mrjam-delivery-adopted.json".source;
    noPlanInstalled= !(builtins.hasAttr "mrjam-promotion/plan.json" after.environment.etc);
    requiresRootPlan=after.systemd.services.mrjam-promotion.unitConfig.ConditionPathExists=="/var/lib/mrjam-promotion/plan.json";
    noForgeWriteCredential=after.systemd.services.mrjam-promotion.serviceConfig.LoadCredential==["forgejo-observer:/var/lib/mrjam-ci-credentials/forgejo-policy-token"];
  };
in {
  modules=baseline.modules++addition;
  evaluation={inherit checks added changed;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
