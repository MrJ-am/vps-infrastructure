# Standalone build of the same script used by the declarative host module.
{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {} }:
let
  cfg = {
    mrjamVpsBackups = { enable = true; promote = true; };
    services.postgresql.package = pkgs.postgresql_17;
  };
  module = import ../hosts/mrjam-vps/backups.nix {
    config = cfg; inherit pkgs; inherit (pkgs) lib;
  };
in pkgs.writeShellApplication {
  name = "forgejo-backup-single";
  runtimeInputs = [ pkgs.coreutils pkgs.diffutils pkgs.gnutar pkgs.age
    pkgs.util-linux pkgs.git pkgs.postgresql_17 ];
  text = module.config.content.systemd.services.forgejo-backup.script;
  # The host script uses its own fail-fast handling and EXIT trap.
  checkPhase = ''bash -n "$target"'';
}
