# Copy verified public review payloads into separately derived local outputs.
# This is not an unsigned import under their original store identities: the
# new paths are recorded separately, with identical NAR and executable bytes.
# No compiler, strip, patchelf or received program is invoked.
{ nixpkgs, receivedStoreRoot }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  platform = builtins.fromJSON (builtins.readFile ./review-artifacts-20261031.json);
  workers = builtins.fromJSON (builtins.readFile ./review-workers-20261031-03.json);
  roots = platform.roots // workers.roots;
  adopter = "/nix/store/sc6zj2w7gpkqr08yhdyfdisyqlg64ax1-mrjam-admission-adoption-1";
  # Its launcher embeds its own original path; reproduce that already pinned
  # source derivation instead of relocating or rewriting the received launcher.
  supersededArchive = "/nix/store/x5cfbdyys74vyyjchans4fkrqqph8h5a-mrjam-vision-workers-0.1.0-9b6cbe740144";
  selected = builtins.removeAttrs roots [ adopter supersededArchive ];
  glibc = builtins.storePath "/nix/store/dphsh3jff8w6n9p3xbfmkia5krqwv52f-glibc-2.42-103";
in builtins.mapAttrs (original: narHash:
  let
    source = builtins.path {
      path = receivedStoreRoot + original;
      name = "received-" + builtins.baseNameOf original;
      sha256 = narHash;
    };
  in pkgs.runCommand ("mrjam-reviewed-" + builtins.substring 33 (-1) (builtins.baseNameOf original)) {
    allowedReferences = [ glibc ];
    # Retain the original binary's existing dynamic loader and libc closure.
    retainedRuntime = glibc;
    passthru = { originalStorePath = original; originalNarHash = narHash; };
  } ''
    mkdir "$out"
    cp -a ${source}/. "$out/"
    # A fixed-output derivation cannot reference libc. Keep those references in
    # the normal derivation, and compare its NAR before accepting the copy.
    test "$(${pkgs.nix}/bin/nix-hash --type sha256 --base32 "$out")" = ${pkgs.lib.escapeShellArg
      (builtins.convertHash { hash = narHash; toHashFormat = "nix32"; })}
  ''
) selected
