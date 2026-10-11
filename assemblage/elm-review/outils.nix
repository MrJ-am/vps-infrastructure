{ pkgs }:
let
  lock = builtins.fromJSON (builtins.readFile ./outils.lock.json);
  nouveaux = builtins.filter (p: p ? nix_sha256) lock.elm;
in
assert pkgs.elmPackages.elm-review.version == lock.cli.version;
assert pkgs.elmPackages.elm-review.npmDepsHash == lock.cli.npmHash;
{
  cli = pkgs.elmPackages.elm-review;
  sources = pkgs.linkFarm "mrjam-sources-elm-review-animator" (map (p: {
    name = "${p.package}/${p.version}";
    path = pkgs.fetchzip { inherit (p) url; extension = "zip"; sha256 = p.nix_sha256; };
  }) nouveaux);
}
