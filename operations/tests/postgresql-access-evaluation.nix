{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-postgresql-access.nix {
      system.stateVersion = "26.05";
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
    } ] ++ extra;
  }).config;
  valid = config: lib.all (entry: entry.assertion) config.assertions;
  slot = { enable = true;
    artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-server";
    runtimeConfigStorePath = "/nix/store/11111111111111111111111111111111-synthetic-runtime";
  };
  fixture = { pkgs, ... }: {
    services.postgresql = {
      enable = true;
      package = pkgs.postgresql_17;
      dataDir = "/var/lib/postgresql/17";
      authentication = ''
        local all postgres peer
        local all all reject
      '';
      identMap = "existing_map existing_user existing_role\n";
      ensureDatabases = [ "retained_database" ];
      ensureUsers = [ { name = "retained_role"; } ];
    };
    services.mrjamRust = { enable = true; slots.blue = slot; slots.green = slot; };
    services.mrjamPostgresqlAccess = { enable = true;
      slots.blue.mateval = { database = "matheval"; role = "matheval_app"; };
      slots.green.mateval = { database = "matheval"; role = "matheval_app"; };
      slots.blue.vision = { database = "vision"; role = "vision"; };
    };
  };
  off = evaluate [ ];
  baseline = evaluate [ fixture { services.mrjamPostgresqlAccess.enable = lib.mkForce false; } ];
  enabled = evaluate [ fixture ];
  pg = enabled.services.postgresql;
  tcpRules = text: builtins.filter (line:
    builtins.match "[[:space:]]*host.*" line != null) (lib.splitString "\n" text);
  checks = {
    disabledKeepsPostgresqlOff = !off.services.postgresql.enable;
    disabledCreatesNoRole = off.services.postgresql.ensureUsers == [ ];
    fixtureValid = valid enabled;
    packageMajorPreserved = lib.versions.major pg.package.version == "17";
    stateVersionPreserved = enabled.system.stateVersion == "26.05";
    dataDirectoryPreserved = pg.dataDir == "/var/lib/postgresql/17";
    databasesPreserved = pg.ensureDatabases == [ "retained_database" ];
    rolesPreserved = map (entry: entry.name) pg.ensureUsers == [ "retained_role" ];
    existingAuthenticationPreserved = lib.hasInfix "local all postgres peer\nlocal all all reject\n" pg.authentication;
    existingIdentityPreserved = lib.hasInfix "existing_map existing_user existing_role" pg.identMap;
    bothSlotsMapped = lib.hasInfix "mrjam_rust_slots mrjam-rust-blue matheval_app" pg.identMap
      && lib.hasInfix "mrjam_rust_slots mrjam-rust-green matheval_app" pg.identMap;
    sharedHbaRuleOnlyOnce = builtins.length (builtins.filter (line:
      line == ''local "matheval" "matheval_app" peer map=mrjam_rust_slots'') (lib.splitString "\n" pg.authentication)) == 1;
    noTcpAccessAdded = tcpRules pg.authentication == tcpRules baseline.services.postgresql.authentication;
    tcpListenerUnchanged = pg.enableTCPIP == baseline.services.postgresql.enableTCPIP
      && pg.settings.listen_addresses == baseline.services.postgresql.settings.listen_addresses;
    noSqlMigrationAdded = enabled.systemd.services.postgresql-setup.postStart == "";
    unavailableSlotRejected = !(valid (evaluate [ fixture {
      services.mrjamRust.slots.green.enable = lib.mkForce false;
    } ]));
    privilegedRoleRejected = !(valid (evaluate [ fixture {
      services.mrjamPostgresqlAccess.slots.blue.vision.role = lib.mkForce "postgres";
    } ]));
    replacedHbaRejected = !(valid (evaluate [ fixture {
      services.postgresql.authentication = lib.mkForce "local all all reject\n";
    } ]));
    extraIdentityRejected = !(valid (evaluate [ fixture {
      services.postgresql.identMap = lib.mkAfter "mrjam_rust_slots foreign_user vision\n";
    } ]));
    extraHbaRejected = !(valid (evaluate [ fixture {
      services.postgresql.authentication = lib.mkAfter "local all all peer map=mrjam_rust_slots\n";
    } ]));
    sharedRoleAcrossDatabasesRejected = !(valid (evaluate [ fixture {
      services.mrjamPostgresqlAccess.slots.green.vision = { database = "another_database"; role = "vision"; };
    } ]));
  };
in if lib.all (value: value) (builtins.attrValues checks) then checks
else throw "PostgreSQL peer checks failed: ${builtins.toJSON (lib.filterAttrs (_: value: !value) checks)}"
