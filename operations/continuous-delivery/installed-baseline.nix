# Reproduce the installed host before extending delivery. Public code and paths
# only: no runtime data, credential contents or activation during evaluation.
{ nixpkgs ? /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source }:
let
  lib = (import nixpkgs { }).lib;
  frozen = builtins.storePath "/nix/store/dnir95r62s6xi57dcygv80fqhirkhzas-mrjam-protected-delivery-recipe-1";
  installed = builtins.storePath "/nix/store/dzwcbxfzzq41ipd23wy91hp309cg72z3-mrjam-protected-delivery-recipe-1";
  baseline = import (frozen + "/operations/ci/continuous-delivery-v1/acceptance-host.nix");
  control = {
    acceptance = "/nix/store/mhld79j2r14kpc3dchh3sv5mlzw2kgys-mrjam-separated-acceptance-services-1";
    preparation = "/nix/store/h9qrds704z40b4dn6bypk3b8x8nkrl78-mrjam-delivery-preparation-1";
    stack = "/nix/store/8mgrb0z9l1fxsjnxzrh59ib0pw1qqq81-mrjam-protected-delivery-stack-1";
    staging = "/nix/store/axj29fss56nxj78inn3k8wzj7cyj928m-mrjam-protected-staging-service-1";
  };
  modules = baseline.modules ++ [
    (import (installed + "/operations/ci/continuous-delivery-v1/delivery-control-plane.nix") { inherit control; })
    (frozen + "/operations/ci/continuous-delivery-v1/delivery-vise-backup-baseline.nix")
    ({ lib, ... }: {
      mrjamVpsApplications.activeSlot = lib.mkOverride (-10) "blue";
      mrjamVpsApplications.slots = {
        blue = lib.mkOverride (-10) "/nix/store/hlzia0qhs00xqhdwqh2z0j41ywmd5dv0-mrjam-runtime-blue";
        green = lib.mkOverride (-10) "/nix/store/d9p7cw8icyviyilbfiapc0mj1ks9qmvi-mrjam-runtime-green";
      };
      services.mrjamRust.slots = {
        blue.artifactStorePath = lib.mkOverride (-10) "/nix/store/s7jifv4bgzbgjddfsfq20x2vkjmvjc6x-mrjam-delivery-server-76cfaec0736c";
        green.artifactStorePath = lib.mkOverride (-10) "/nix/store/qscwq2h3brh011sc22x0530ibkh3invs-mrjam-delivery-server-6135a1bda1eb";
      };
      services.mrjamIntakePreparation.adopted = lib.mkOverride (-10)
        (builtins.storePath "/nix/store/2ny4527xzy4d9aljs805j037kydnypbc-mrjam-adopted-source.json");
      systemd.services.mrjam-rust-blue.wantedBy = lib.mkOverride (-10) [ "multi-user.target" ];
      systemd.services.mrjam-rust-green.wantedBy = lib.mkOverride (-10) [ ];
      system.extraDependencies = map builtins.storePath [
        "/nix/store/hlzia0qhs00xqhdwqh2z0j41ywmd5dv0-mrjam-runtime-blue"
        "/nix/store/d9p7cw8icyviyilbfiapc0mj1ks9qmvi-mrjam-runtime-green"
        "/nix/store/s7jifv4bgzbgjddfsfq20x2vkjmvjc6x-mrjam-delivery-server-76cfaec0736c"
        "/nix/store/qscwq2h3brh011sc22x0530ibkh3invs-mrjam-delivery-server-6135a1bda1eb"
      ];
    })
  ];
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = modules ++ extra;
  }).config;
in { inherit nixpkgs modules evaluate; }
