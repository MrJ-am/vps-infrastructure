{ system ? "x86_64-linux" }:
let
  input = (builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile ../../flake.lock))).nodes.nixpkgs.locked;
  source = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${input.rev}.tar.gz";
    sha256 = input.narHash;
  };
in
assert system == "x86_64-linux";
assert input.type == "github" && input.owner == "NixOS" && input.repo == "nixpkgs";
assert input.rev == "6f06d204d8f2d8761d9da78778745974a3216381";
assert input.narHash == "sha256-loLMnbbS4KhmG2ln9EY6f0YMNCA273Yx02oWYQ9IMeE=";
import source { inherit system; config = { }; overlays = [ ]; }
