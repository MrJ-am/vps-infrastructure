# Evaluate one component at a time to release its Nix evaluation heap afterwards.
{ nixpkgs, component ? null, includeVise ? false }:
let matrix = import ./evaluation.nix { inherit nixpkgs includeVise; };
in if component == null then builtins.attrNames matrix.components
   else matrix.components.${component}
