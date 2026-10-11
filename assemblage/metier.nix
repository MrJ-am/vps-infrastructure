# Sources exactes fournies par l'assembleur ; aucun fetch de branche ni vendor.
{ pkgs, vision, matheval, revisionInfrastructure }:
assert pkgs.sbcl.version == "2.6.4";
assert builtins.match "[0-9a-f]{40}" revisionInfrastructure != null;
let
  sourcesVision = pkgs.lib.cleanSourceWith {
    src = vision;
    filter = path: type:
      let p = pkgs.lib.removePrefix (toString vision + "/") (toString path); in
      type == "directory" && (toString path == toString vision || p == "src" || p == "docs")
      || type == "regular" && (p == "vision.asd" || pkgs.lib.hasPrefix "src/" p && pkgs.lib.hasSuffix ".lisp" p
        || builtins.elem p [ "docs/CONTRAT-SEANCE.md" "docs/tutoriel.json" "docs/outils.json" "docs/MCP.md" ]);
  };
  sourcesMatheval = pkgs.lib.cleanSourceWith {
    src = matheval;
    filter = path: type:
      let p = pkgs.lib.removePrefix (toString matheval + "/") (toString path); in
      type == "directory" && (toString path == toString matheval || p == "lisp")
      || type == "regular" && (p == "matheval.asd" || pkgs.lib.hasPrefix "lisp/" p && pkgs.lib.hasSuffix ".lisp" p);
  };
in
pkgs.stdenv.mkDerivation {
  pname = "mrjam-metier";
  version = builtins.substring 0 12 revisionInfrastructure;
  src = pkgs.lib.cleanSourceWith {
    src = ../.;
    filter = path: type:
      let relatif = pkgs.lib.removePrefix (toString ../. + "/") (toString path); in
      type == "directory" && (toString path == toString ../. || relatif == "assemblage" || relatif == "lisp" || pkgs.lib.hasPrefix "lisp/" relatif)
      || builtins.elem relatif [ "mrjam-metier.asd" "mrjam-native.asd" "mrjam-courriel.asd" "mrjam-identite.asd"
        "assemblage/charger.lisp" "assemblage/construire.lisp" ]
      || pkgs.lib.hasPrefix "lisp/" relatif && pkgs.lib.hasSuffix ".lisp" relatif;
  };
  nativeBuildInputs = [ pkgs.sbcl ];
  dontConfigure = true;
  dontStrip = true; # Le core est appendu au runtime ELF ; strip détruirait l'image.
  dontPatchELF = true;
  buildPhase = ''
    runHook preBuild
    mkdir -p "$TMPDIR/atelier/vision" "$TMPDIR/atelier/M-moire" "$TMPDIR/fasl" "$out/bin" "$out/share/mrjam"
    cp -R ${sourcesVision}/. "$TMPDIR/atelier/vision/"
    cp -R ${sourcesMatheval}/. "$TMPDIR/atelier/M-moire/"
    export MRJAM_ATELIER="$TMPDIR/atelier/"
    export MRJAM_EXECUTABLE="$out/bin/mrjam-metier"
    export MRJAM_BUILD_METADATA="$out/share/mrjam/compilation.json"
    export ASDF_SOURCE_REGISTRY='(:source-registry :ignore-inherited-configuration)'
    export ASDF_OUTPUT_TRANSLATIONS="(:output-translations (t \"$TMPDIR/fasl/\") :ignore-inherited-configuration)"
    # Aucun DSO, DSN, credential ni accès métier dans ce processus de build.
    sbcl --script assemblage/construire.lisp
    test -x "$out/bin/mrjam-metier"
    sbcl --noinform --non-interactive --eval '(require :asdf)' \
      --eval '(format t "SBCL ~A ASDF ~A~%" (lisp-implementation-version) (asdf:asdf-version))' > "$out/share/mrjam/toolchain"
    printf '%s\n' ${pkgs.lib.escapeShellArg revisionInfrastructure} > "$out/share/mrjam/infrastructure"
    runHook postBuild
  '';
  installPhase = "true";
}
