{ pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
let
  validator = import ./aligned-validator.nix { inherit pkgs; };
  prepared = ../../../.local/deployment-20261101/aligned-proposal-003;
  proposal = "04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d";
  source = assert builtins.hashFile "sha256" (prepared + "/manifest.json") == proposal;
    pkgs.runCommand "mrjam-aligned-public-source-proposal-003" {} ''
      mkdir "$out"
      cp -r --no-preserve=mode,ownership ${prepared}/. "$out/"
    '';
  closure = pkgs.closureInfo { rootPaths = [ validator ]; };
in { inherit validator source proposal closure; }
