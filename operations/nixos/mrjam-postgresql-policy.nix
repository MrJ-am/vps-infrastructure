# Compose independent, declarative HBA blocks ahead of the existing policy.
# This only renders configuration: no SQL, migration or database provisioning.
{ config, lib, ... }:
let
  blocks = config.services.mrjamPostgresqlPolicy.blocks;
  prefix = lib.concatStringsSep "" (builtins.attrValues blocks);
  producers = lib.optional (config.services.mrjamPostgresqlAccess.enable or false) "rust"
    ++ lib.optional (config.services.mrjamVise.enable or false) "vise";
in {
  options.services.mrjamPostgresqlPolicy.blocks = lib.mkOption {
    type = lib.types.attrsOf lib.types.lines;
    default = { };
    description = "Closed Rust/ViSe HBA blocks before the preserved host policy; new producers require a reviewed code change.";
  };
  config = lib.mkIf (blocks != { }) {
    assertions = [
      { assertion = builtins.attrNames blocks == producers;
        message = "mrjamPostgresqlPolicy: only blocks from the enabled Rust/ViSe modules are accepted; unknown or orphan blocks are refused."; }
      { assertion = config.services.postgresql.enable;
        message = "mrjamPostgresqlPolicy: requires the independently configured PostgreSQL service."; }
      { assertion = lib.all (block: block != "" && lib.hasSuffix "\n" block) (builtins.attrValues blocks);
        message = "mrjamPostgresqlPolicy: each block must be nonempty and end with a newline."; }
      { assertion = lib.hasPrefix prefix config.services.postgresql.authentication;
        message = "mrjamPostgresqlPolicy: the composed rules must precede the existing host policy; overriding or preceding them is refused."; }
    ];
    services.postgresql.authentication = lib.mkBefore prefix;
  };
}
