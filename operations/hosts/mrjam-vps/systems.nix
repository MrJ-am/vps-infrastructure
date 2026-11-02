# Build both exact generations before the cutover window. No activation entrypoint.
let
  input = (builtins.fromJSON (builtins.readFile ../../compatibility/nixpkgs-vps-observed.lock.json)).input;
  source = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${input.rev}.tar.gz";
    sha256 = input.narHash;
  };
  build = module: (import (source + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ module ];
  }).config.system.build.toplevel;
in
assert input.rev == "c5c4a43b0e8056328ec4529f735cabdb8f1942bb";
assert input.narHash == "sha256-u6z9VTZA4Kf3RkHQo9sQI7NI4Ei/uiU9vrMqOiwWP1Y=";
{
  staged = build ./candidate.nix;
  promoted = build ./candidate-promoted.nix;
}
