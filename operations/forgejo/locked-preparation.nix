# The preparation package has its own reviewed toolchain. Importing the module
# on an older host must not substitute that host's Forgejo, runner or renderer.
{ system ? "x86_64-linux" }:
let
  flakeLock = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile ../../flake.lock));
  versions = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile ./versions.lock.json));
  input = flakeLock.nodes.nixpkgs.locked;
  # Fixed-output source: reusable from the store without a per-user Git cache.
  # The revision and NAR hash are the same as the qualified flake input.
  source = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${input.rev}.tar.gz";
    sha256 = input.narHash;
  };
  pkgs = import source { inherit system; config = { }; overlays = [ ]; };
in
assert system == "x86_64-linux"; # Only the qualified platform, no cross build.
assert input.type == "github" && input.owner == "NixOS" && input.repo == "nixpkgs";
assert input.rev == versions.nixpkgs_revision;
assert input.narHash == "sha256-loLMnbbS4KhmG2ln9EY6f0YMNCA273Yx02oWYQ9IMeE=";
pkgs.callPackage ./package.nix { }
