# Data artifact only: building this output never opens a database or runs SQL.
{ nixpkgs, materialized }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  inputs = builtins.path { path = materialized; name = "mrjam-vision-ordering-source"; };
  source = builtins.fromJSON (builtins.readFile (inputs + "/source.json"));
  migration = inputs + "/004_ordre_rejeu.sql";
  sha256 = "7cc54d48e53c1a32712234bd17ed88f7da8da7807c4a8181f94908021710e0e8";
  revision = "c7056949832a4b00939c7ec62617bf3d64d3d2ce";
  manifest = pkgs.writeText "mrjam-vision-ordering-manifest.json" (builtins.toJSON {
    schema_version = 1; artifact = "vision-journal-ordering-004";
    source_revision = revision; source_path = "journal/004_ordre_rejeu.sql";
    payload_sha256."share/mrjam/vision-journal/004_ordre_rejeu.sql" = sha256;
    compatible_replay_elf_sha256 = "5afcb57458af7c627012677e38961adc532ad62fa99048bdb746c8d069f4caae";
    required_prior_migrations = [ "001_effacements.sql" "002_reprise.sql" "003_archivage_rejeu.sql" ];
    data_rewrite = false; execution_supported = false; deployment_authorized = false;
  });
in
assert source == { source_revision = revision; source_path = "journal/004_ordre_rejeu.sql"; inherit sha256; };
assert builtins.hashFile "sha256" migration == sha256;
pkgs.runCommand "mrjam-vision-journal-ordering-004-${builtins.substring 0 12 revision}" {} ''
  install -Dm444 ${migration} "$out/share/mrjam/vision-journal/004_ordre_rejeu.sql"
  install -Dm444 ${manifest} "$out/artifact.json"
  cmp ${migration} "$out/share/mrjam/vision-journal/004_ordre_rejeu.sql"
''
