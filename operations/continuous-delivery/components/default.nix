{ source, revision ? null, pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
let
  tools = pkgs.callPackage ../../builds/toolchains.nix {};
  inputs = source + "/.delivery-inputs";
  support = builtins.path {
    path = ./.;
    name = "component-build-support";
    filter = path: type:
      (type == "directory" && path == toString ./.) ||
      (type == "regular" && builtins.elem (builtins.baseNameOf path) [ "build.py" "prepare.py" ]);
  };
  rawBuild = kind: pkgs.stdenv.mkDerivation {
    pname = "mrjam-${kind}";
    version = "1";
    dontUnpack = true;
    strictDeps = true;
    nativeBuildInputs = [ pkgs.python3 tools.node pkgs.elmPackages.elm pkgs.elmPackages.elm-format ]
      ++ pkgs.lib.optionals (kind == "vise") [ tools.rust pkgs.postgresql_17 ];
    buildPhase = ''
      runHook preBuild
      python3 ${support}/build.py ${kind} ${inputs} "$out" ${source}
      runHook postBuild
    '';
    dontInstall = true;
    # Check the exact bytes that will be served, rather than changing the source tests.
    disallowedReferences = [ inputs source ];
  };
  # Final manifests bind runtime bytes after ELF fixup/stripping. Keeping this
  # finalizer separate also avoids recompiling applications for metadata edits.
  build = kind:
    assert pkgs.lib.assertMsg (kind != "frontends" ||
      (revision != null && builtins.match "[0-9a-f]{40}" revision != null))
      "frontends requires revision = exact infrastructure commit";
    pkgs.runCommand "mrjam-${kind}-artifacts" {
    nativeBuildInputs = [ pkgs.python3 ];
    disallowedReferences = [ inputs source ];
  } ''
    mkdir -p "$out"
    cp -R ${rawBuild kind}/. "$out/"
    chmod -R u+w "$out"
    python3 ${./record.py} ${kind} ${inputs} "$out" \
      ${pkgs.lib.escapeShellArg (if revision == null then "" else revision)} ${../../builds/toolchains.lock.json}
  '';
in {
  frontends = build "frontends";
  vise = build "vise";
}
