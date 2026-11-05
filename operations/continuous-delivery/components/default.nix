{ source, pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
let
  tools = pkgs.callPackage ../../builds/toolchains.nix {};
  inputs = source + "/.delivery-inputs";
  build = kind: pkgs.stdenv.mkDerivation {
    pname = "mrjam-${kind}";
    version = "1";
    dontUnpack = true;
    strictDeps = true;
    nativeBuildInputs = [ pkgs.python3 tools.node pkgs.elmPackages.elm pkgs.elmPackages.elm-format ]
      ++ pkgs.lib.optionals (kind == "vise") [ tools.rust pkgs.postgresql_17 ];
    buildPhase = ''
      runHook preBuild
      python3 ${./.}/build.py ${kind} ${inputs} "$out" ${source}
      runHook postBuild
    '';
    dontInstall = true;
    # Check the exact bytes that will be served, rather than changing the source tests.
    disallowedReferences = [ inputs source ];
  };
in {
  frontends = build "frontends";
  vise = build "vise";
}
