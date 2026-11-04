# Fixed repair on the delivered PR4 generation; no candidate inputs.
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {}; lib=pkgs.lib;
  recipe=/nix/store/hnrcwyy81idbbwlnzz9455fbm0989hpy-mrjam-protected-delivery-recipe-1;
  baseline=import (recipe+"/operations/ci/continuous-delivery-v1/acceptance-host.nix");
  control={
    acceptance="/nix/store/vkvzk7vd6w5jawhda3vz7p88d5wpdqm0-mrjam-separated-acceptance-services-1";
    preparation="/nix/store/aij7vndm5yqsm98bh1n7bccb3gp2z0hn-mrjam-delivery-preparation-1";
    staging="/nix/store/zk671bry18xn1ahfhjy8y2yg31mpli23-mrjam-protected-staging-service-1";
  };
  preparation="/nix/store/j7cid9hslbnc29n4kmynjv8sm12y01kb-mrjam-delivery-preparation-1";
  evaluate=mods: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=mods;}).config;
  base=evaluate (baseline.modules++[(import (recipe+"/operations/ci/continuous-delivery-v1/delivery-control-plane.nix") {inherit control;})]);
  slots={
    blue={runtime="/nix/store/j4fh34y2iqfdgw4zvzf57mcj1xis78rx-mrjam-runtime-blue";server="/nix/store/c7hgzdnhddl90hdp1a37kwlkj9xrpyyn-mrjam-delivery-server-e06f030310ae";};
    green={runtime="/nix/store/d9p7cw8icyviyilbfiapc0mj1ks9qmvi-mrjam-runtime-green";server="/nix/store/qscwq2h3brh011sc22x0530ibkh3invs-mrjam-delivery-server-6135a1bda1eb";};
  };
  names=["blue" "green"];
  overlay={
    mrjamVpsApplications.activeSlot=lib.mkOverride (-10) "green";
    mrjamVpsApplications.slots=lib.genAttrs names (s: lib.mkIf (slots.${s}.runtime!=base.mrjamVpsApplications.slots.${s}) (lib.mkOverride (-10) slots.${s}.runtime));
    services.mrjamRust.slots=lib.genAttrs names (s: {artifactStorePath=lib.mkIf (slots.${s}.server!=base.services.mrjamRust.slots.${s}.artifactStorePath) (lib.mkOverride (-10) slots.${s}.server);});
    services.mrjamIntakePreparation.adopted=lib.mkOverride (-10) (builtins.storePath /nix/store/v2qj31slhqs948a5ihd7yrva9nhhp7pc-mrjam-adopted-source.json);
    systemd.services=lib.genAttrs (map (s: "mrjam-rust-${s}") names) (n: {wantedBy=lib.mkOverride (-10) (lib.optional (n=="mrjam-rust-green") "multi-user.target");});
    system.extraDependencies=lib.concatMap (s:
      lib.optional (slots.${s}.server!=base.services.mrjamRust.slots.${s}.artifactStorePath) (builtins.storePath slots.${s}.server)
      ++lib.optional (slots.${s}.runtime!=base.mrjamVpsApplications.slots.${s}) (builtins.storePath slots.${s}.runtime)) names;
  };
  modules=c: baseline.modules++[(import (recipe+"/operations/ci/continuous-delivery-v1/delivery-control-plane.nix") {control=c;}) overlay];
  before=evaluate (modules control); after=evaluate (modules (control//{inherit preparation;}));
  units=builtins.attrNames before.systemd.units;
  changed=builtins.filter (n: before.systemd.units.${n}.text!=after.systemd.units.${n}.text) units;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/cx70ninizmzz3lmx00p6rgr17g6wna97-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    unitsUnchanged=builtins.attrNames after.systemd.units==units;
    onlyPreparationChanged=changed==["mrjam-delivery-preparation.service"];
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    adoptedUnchanged=before.environment.etc."mrjam-delivery-adopted.json".source==after.environment.etc."mrjam-delivery-adopted.json".source;
    credentialsUnchanged=before.systemd.services.mrjam-delivery-preparation.serviceConfig.LoadCredential==after.systemd.services.mrjam-delivery-preparation.serviceConfig.LoadCredential;
  };
in {
  evaluation={inherit checks changed;previous=toString before.system.build.toplevel;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
