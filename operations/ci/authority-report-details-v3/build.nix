{ pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
let
  old = builtins.storePath /nix/store/19r3a6ylzp32vg3bkfr9wfhd1n8cwm71-mrjam-validation-authority-credentials-2;
  text = builtins.readFile (old + "/lib/signer.py");
  path = builtins.head (builtins.match ".*POLICY_PATH='([^']+)'.*" text);
  authorityPolicy = builtins.fromJSON (builtins.readFile (builtins.storePath path));
in import ./package.nix { inherit pkgs authorityPolicy; producerBinding = authorityPolicy.producer; }
