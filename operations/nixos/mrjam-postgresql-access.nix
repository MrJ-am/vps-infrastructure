# Additional local peer mappings only. Existing databases, dataDir and package
# remain owned by the authoritative PostgreSQL configuration.
{ config, lib, ... }:
let
  cfg = config.services.mrjamPostgresqlAccess;
  sqlName = lib.types.strMatching "[a-z][a-z0-9_]{0,62}";
  connectionType = lib.types.submodule {
    options = {
      database = lib.mkOption { type = sqlName; };
      role = lib.mkOption { type = sqlName; };
    };
  };
  capabilities = [ "mateval" "matevalAdministration" "vision"
    "visionAdministration" "visionJournal" "audition" ];
  workerIdentities = {
    visionArchive = { user = "mrjam-vision-archive"; enabled = config.services.mrjamVisionArchive.enable or false; };
    visionReplayJournal = { user = "mrjam-vision-replay"; enabled = config.services.mrjamVisionReplay.enable or false; };
    visionReplayCycle = workerIdentities.visionReplayJournal;
    visionReplayClosure = workerIdentities.visionReplayJournal;
    visionCycle = { user = "mrjam-vision-cycle"; enabled = config.services.mrjamVisionCycle.enable or false; };
    visionCycleJournal = workerIdentities.visionCycle;
    visionClosure = { user = "mrjam-vision-closure"; enabled = config.services.mrjamVisionClosure.enable or false; };
    visionClosureJournal = workerIdentities.visionClosure;
    visionAdmission = { user = "mrjam-vision-admission"; enabled = config.services.mrjamVisionAdmission.enable or false; };
    visionAdmissionAdministration = workerIdentities.visionAdmission;
  };
  slotType = lib.types.submodule {
    options = lib.genAttrs capabilities (_: lib.mkOption {
      type = lib.types.nullOr connectionType;
      default = null;
      description = "Explicit existing SQL database/role; no role or database is created.";
    });
  };
  rows = lib.concatMap (slot: lib.mapAttrsToList (capability: connection: {
    inherit slot capability;
    inherit (connection) database role;
    user = "mrjam-rust-${slot}";
  }) (lib.filterAttrs (_: value: value != null) cfg.slots.${slot})) [ "blue" "green" ]
  ++ lib.mapAttrsToList (capability: connection: {
    slot = null; inherit capability;
    user = workerIdentities.${capability}.user;
    inherit (connection) database role;
  }) (lib.filterAttrs (_: connection: connection != null) cfg.workers);
  safeName = name: !(lib.hasPrefix "pg_" name)
    && !(builtins.elem name [ "postgres" "template0" "template1" "root" "nobody" "all" "replication" ]);
  mapName = "mrjam_rust_slots";
  hbaLines = lib.unique (map (row: ''local "${row.database}" "${row.role}" peer map=${mapName}'') rows);
  hbaBlock = lib.concatStringsSep "\n" hbaLines + "\n";
  identLines = lib.unique (map (row: "${mapName} ${row.user} ${row.role}") rows);
  identBlock = lib.concatStringsSep "\n" identLines + "\n";
  effectiveMap = builtins.filter (line:
    builtins.match "[[:space:]]*${mapName}[[:space:]].*" line != null
  ) (lib.splitString "\n" config.services.postgresql.identMap);
  effectiveHba = builtins.filter (line: lib.hasInfix "map=${mapName}" line)
    (lib.splitString "\n" config.services.postgresql.authentication);
in {
  imports = [ ./mrjam-rust.nix ];
  options.services.mrjamPostgresqlAccess = {
    enable = lib.mkEnableOption "explicit peer mappings for prebuilt Rust slots and lifecycle workers";
    slots = {
      blue = lib.mkOption { type = slotType; default = { }; };
      green = lib.mkOption { type = slotType; default = { }; };
    };
    workers = lib.genAttrs (builtins.attrNames workerIdentities)
      (_: lib.mkOption { type = lib.types.nullOr connectionType; default = null; });
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = config.services.postgresql.enable;
        message = "mrjamPostgresqlAccess requires the separately declared existing PostgreSQL service."; }
      { assertion = lib.versions.major config.services.postgresql.package.version == "17";
        message = "mrjamPostgresqlAccess is qualified for PostgreSQL 17; it never changes the package."; }
      { assertion = rows != [ ];
        message = "mrjamPostgresqlAccess requires explicit existing database/role pairs."; }
      { assertion = lib.all (row: safeName row.role && safeName row.database) rows;
        message = "mrjamPostgresqlAccess refuses reserved or privileged database/role names."; }
      { assertion = lib.all (row: builtins.length (lib.unique (map (other: other.database)
            (builtins.filter (other: other.role == row.role) rows))) == 1) rows;
        message = "mrjamPostgresqlAccess requires each SQL role to belong to one declared database, preventing cross-slot database access."; }
      { assertion = lib.all (row: if row.slot == null
          then workerIdentities.${row.capability}.enabled
          else config.services.mrjamRust.enable && config.services.mrjamRust.slots.${row.slot}.enable) rows;
        message = "mrjamPostgresqlAccess requires each declared local Rust identity."; }
      { assertion = lib.hasPrefix hbaBlock config.services.postgresql.authentication;
        message = "mrjamPostgresqlAccess rules must precede existing catch-all rules; conflicting overrides are refused."; }
      { assertion = lib.sort builtins.lessThan effectiveMap == lib.sort builtins.lessThan identLines;
        message = "mrjamPostgresqlAccess refuses another identity mapping under its reserved map name."; }
      { assertion = lib.sort builtins.lessThan effectiveHba == lib.sort builtins.lessThan hbaLines;
        message = "mrjamPostgresqlAccess refuses another HBA rule using its reserved identity map."; }
    ];
    # One shared map is necessary: duplicate HBA entries for blue/green would
    # cause the second slot to be rejected after the first matching HBA rule.
    services.postgresql.authentication = lib.mkBefore hbaBlock;
    services.postgresql.identMap = lib.mkBefore identBlock;
  };
}
