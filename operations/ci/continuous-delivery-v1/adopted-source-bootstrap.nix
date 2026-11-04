{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {} }:
# Initial adopted source matches the reviewed, signed release currently served.
# A later promotion must replace this descriptor in the same system generation.
pkgs.writeText "mrjam-adopted-source.json" (builtins.toJSON {
  schema_version=1;
  source=builtins.storePath "/nix/store/hqh3b9b2z13rqbkn4hy73m2vln3apl1r-mrjam-aligned-public-source-proposal-003";
  policy=builtins.storePath "/nix/store/wpwr3rby105fha7vckv6dywfnyqmsr8n-mrjam-aligned-validator-policy.json";
  proposal_sha256="04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d";
})
