# Même Nixpkgs verrouillé que l'assemblage ; sources seulement, pas de tool MCP.
{ pkgs }:
let
  lock = builtins.fromJSON (builtins.readFile ./dependances.lock.json);
  sources = builtins.listToAttrs (map (b: {
    name = b.name;
    value = assert toString pkgs.sbclPackages.${b.name}.src == b.src;
      pkgs.sbclPackages.${b.name}.src;
  }) lock.bibliotheques);
in assert pkgs.sbcl.version == lock.sbcl; sources
