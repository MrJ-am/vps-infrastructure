# Même Nixpkgs que le VPS constaté, pas la source des anciens tests Keycloak.
{ pkgs }:
assert pkgs.sbcl.version == "2.6.4";
assert pkgs.postgresql_17.version == "17.11";
pkgs.linkFarm "mrjam-outils-qualification" [
  { name = "sbcl"; path = pkgs.sbcl; }
  { name = "postgresql"; path = pkgs.lib.getLib pkgs.postgresql_17; }
  { name = "openssl"; path = pkgs.lib.getLib pkgs.openssl; }
  { name = "sqlite"; path = pkgs.lib.getLib pkgs.sqlite; }
  { name = "curl"; path = pkgs.curl; }
  { name = "age"; path = pkgs.age; }
]
