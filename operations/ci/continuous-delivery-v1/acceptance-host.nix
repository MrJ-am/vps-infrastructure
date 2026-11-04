let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib=(import nixpkgs {}).lib;
  baseline=import ./accepted-e06-promoted-host.nix;
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=baseline.modules++extra;}).config;
  installed=builtins.appendContext "/nix/store/5krkhb1chsm97vvcvjra0zbbqnikypc4-mrjam-separated-acceptance-services-1" {
    "/nix/store/ifwy8ybnxryyypcvi8iyfxskq9wic67j-mrjam-separated-acceptance-services-1.drv"={outputs=["out"];};
  };
  addition=[./acceptance-services-module.nix {
    systemd.services=lib.genAttrs (map (stage: "mrjam-acceptance-${stage}") stages) (name: {
      serviceConfig.ExecStart=lib.mkOverride 20 "${installed}/bin/${name}";
    });
  }];before=evaluate [];after=evaluate addition;
  names=builtins.attrNames before.systemd.units;
  added=lib.subtractLists names (builtins.attrNames after.systemd.units);
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  stages=["mirror" "review" "merge" "sync"];
  units=map (stage: after.systemd.services."mrjam-acceptance-${stage}".serviceConfig) stages;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/yfq7p6syfj101c8iiimpnp7cajd2xga2-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyAcceptanceUnitsAdded=added==lib.sort builtins.lessThan (lib.concatMap (stage: ["mrjam-acceptance-${stage}.service" "mrjam-acceptance-${stage}.timer"]) stages);
    existingUnitsUnchanged=changed==[];
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    adoptedUnchanged=before.environment.etc."mrjam-delivery-adopted.json".source==after.environment.etc."mrjam-delivery-adopted.json".source;
    isolatedCredentials=lib.all (stage:
      let creds=after.systemd.services."mrjam-acceptance-${stage}".serviceConfig.LoadCredential;
      in creds==["github-app:/var/lib/mrjam-github-app/app-credentials.json" "forgejo-observer:/var/lib/mrjam-ci-credentials/forgejo-policy-token"]
        ++lib.optional (stage!="sync") "forgejo-role:/var/lib/mrjam-delivery-credentials/forgejo-${stage}-token") stages;
    captureReadOnly=lib.all (unit: unit.ProtectSystem=="strict" && !(unit ? ReadWritePaths)) units;
    privilegedSocketsMasked=lib.all (unit: lib.all (p: builtins.elem p unit.InaccessiblePaths)
      ["-/run/systemd/private" "-/run/dbus/system_bus_socket" "-/nix/var/nix/daemon-socket" "-/run/mrjam-validation-authority"]) units;
  };
in {
  modules=baseline.modules++addition;
  evaluation={inherit checks added changed;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
