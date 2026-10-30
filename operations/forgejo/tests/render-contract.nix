{ runCommand, python3, callPackage }:
let
  preparation = callPackage ../package.nix { };
in
runCommand "mrjam-forgejo-org-render-contract" { nativeBuildInputs = [ python3 ]; } ''
  python3 ${./test_renderer.py} ${preparation.render} > "$out"
''
