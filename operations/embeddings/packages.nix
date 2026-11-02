# Reproduce the two exact public store outputs observed on the installed VPS.
# This intentionally uses the host pin, independently of application builds.
{ nixpkgs ? null, system ? "x86_64-linux" }:
let
  lock = (builtins.fromJSON (builtins.readFile ../compatibility/nixpkgs-vps-observed.lock.json)).input;
  source = if nixpkgs != null then nixpkgs else builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${lock.rev}.tar.gz";
    sha256 = lock.narHash;
  };
  pkgs = import source { inherit system; config = { }; overlays = [ ]; };
  python = pkgs.python3.withPackages (ps: [ ps.sentence-transformers ]);
  model = import ./model.nix { inherit pkgs; };
in
assert system == "x86_64-linux";
assert lock.rev == "c5c4a43b0e8056328ec4529f735cabdb8f1942bb";
assert python.outPath == "/nix/store/dbnsh65c9fir9psk7waq3swb3mdh18cr-python3-3.13.15-env";
assert model.outPath == "/nix/store/mwwjyy4vlrwp59a7srjy53x24viksa6z-vision-modele-multilingue-e8f8c211226b";
{ inherit python model; }
