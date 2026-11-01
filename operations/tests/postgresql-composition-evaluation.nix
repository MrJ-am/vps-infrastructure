{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-postgresql-access.nix ../nixos/mrjam-vise.nix
      ({ pkgs, ... }: {
        system.stateVersion = "26.05";
        boot.loader.grub.enable = false;
        fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
        services.postgresql = {
          enable = true; package = pkgs.postgresql_17;
          authentication = "local all postgres peer\nlocal all all reject\n";
        };
      }) extra ];
  }).config;
  setup = {
    services.mrjamRust = { enable = true; slots.blue = {
      enable = true;
      artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-server";
      runtimeConfigStorePath = "/nix/store/11111111111111111111111111111111-synthetic-runtime";
    }; };
    services.mrjamPostgresqlAccess = { enable = true;
      slots.blue.mateval = { database = "synthetic_mateval"; role = "synthetic_mateval_app"; };
    };
    services.mrjamVise = {
      enable = true; artifactRoot = "/nix/store/22222222222222222222222222222222-synthetic-vise";
      adoption = { uid = 978; gid = 978; };
    };
  };
  baseline = evaluate { };
  combined = evaluate setup;
  rustOnly = evaluate { imports = [ setup ]; services.mrjamVise.enable = lib.mkForce false; };
  viseOnly = evaluate { imports = [ setup ]; services.mrjamPostgresqlAccess.enable = lib.mkForce false; };
  valid = config: lib.all (a: a.assertion) config.assertions;
  bad = extra: evaluate { imports = [ setup extra ]; };
  pg = combined.services.postgresql;
  checks = {
    baselineValid = valid baseline;
    combinedValid = valid combined;
    eachIndependentPolicyValid = valid rustOnly && valid viseOnly;
    namedBlocksComposed = builtins.attrNames combined.services.mrjamPostgresqlPolicy.blocks == [ "rust" "vise" ];
    bothBlocksAheadOfHostRules = lib.hasPrefix
      (combined.services.mrjamPostgresqlPolicy.blocks.rust + combined.services.mrjamPostgresqlPolicy.blocks.vise) pg.authentication;
    unchangedHostPolicyTail = lib.hasSuffix baseline.services.postgresql.authentication pg.authentication;
    noRoleDatabaseOrDataDirChange = pg.ensureUsers == baseline.services.postgresql.ensureUsers
      && pg.ensureDatabases == baseline.services.postgresql.ensureDatabases && pg.dataDir == baseline.services.postgresql.dataDir;
    noPostgresPackageChange = pg.package.outPath == baseline.services.postgresql.package.outPath;
    noNetworkListenerChange = pg.settings.listen_addresses == baseline.services.postgresql.settings.listen_addresses;
    noSharedSsoDependency = combined.systemd.services.vise.requires == [ "postgresql.service" ];
    hbaOverrideRejected = !valid (bad { services.postgresql.authentication = lib.mkForce "local all all trust\n"; });
    earlierCatchAllRejected = !valid (bad { services.postgresql.authentication = lib.mkOrder 100 "local all all trust\n"; });
    unknownEarlierBlockRejected = !valid (bad { services.mrjamPostgresqlPolicy.blocks.aaa = "local all etp_carnet trust\n"; });
    alteredViseBlockRejected = !valid (bad { services.mrjamPostgresqlPolicy.blocks.vise = lib.mkForce "local all etp_carnet trust\n"; });
    extendedRustBlockRejected = !valid (bad { services.mrjamPostgresqlPolicy.blocks.rust = lib.mkAfter "local all etp_carnet trust\n"; });
    orphanViseBlockRejected = !valid (bad {
      services.mrjamVise.enable = lib.mkForce false;
      services.mrjamPostgresqlPolicy.blocks.vise = "local all etp_carnet trust\n";
    });
    independentViseRoleRejectedForRust = !valid (bad { services.mrjamPostgresqlAccess.slots.blue.mateval.role = lib.mkForce "etp_carnet"; });
    independentViseDatabaseRejectedForRust = !valid (bad { services.mrjamPostgresqlAccess.slots.blue.mateval.database = lib.mkForce "etp_carnet"; });
  };
in assert builtins.all (v: v) (builtins.attrValues checks); checks
