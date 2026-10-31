{ lib, stdenv, python3, callPackage, elmPackages
, materialized, sourceLock, expectedManifestSha256
}:
let
  tools = callPackage ./toolchains.nix { };
  inputs = builtins.path { path = materialized; name = "mrjam-pinned-public-frontends"; };
  lock = builtins.fromJSON (builtins.readFile sourceLock);
  support = builtins.path {
    path = ./.;
    name = "mrjam-frontend-build-support";
    filter = path: type:
      (type == "directory" && path == toString ./.) ||
      (type == "regular" && builtins.elem (builtins.baseNameOf path) [
        "frontend_inputs.py" "frontend_artifact.py" "check_frontend_site.py" "select_sources.py" "prepare.py" "toolchains.lock.json"
      ]);
  };
  frontend = name: stdenv.mkDerivation {
    pname = "mrjam-${name}-elm";
    version = builtins.substring 0 12 lock.frontends.${name}.source_commit;
    dontUnpack = true;
    nativeBuildInputs = [ python3 elmPackages.elm tools.node ] ++ lib.optional (name == "vision") elmPackages.elm-format;
    disallowedReferences = [ inputs ];
    configurePhase = ''
      runHook preConfigure
      python ${support}/frontend_inputs.py --inputs ${inputs} --source-lock ${sourceLock} --manifest-sha256 ${lib.escapeShellArg expectedManifestSha256}
      cp -R ${inputs}/applications/${name} application
      cp -R ${inputs}/styles/${lock.frontends.${name}.style_revision} style
      cp -R ${inputs}/elm-home "$TMPDIR/elm-home"
      chmod -R u+w application style "$TMPDIR/elm-home"
      export ELM_HOME="$TMPDIR/elm-home" HOME="$TMPDIR/build-home" GHCRTS=-N2
      export GITHUB_SHA=${lock.frontends.${name}.source_commit}
      mkdir -p "$HOME"
      test "$(elm --version)" = 0.19.1
      test "$(node --version)" = v24.19.0
      runHook postConfigure
    '';
    buildPhase = if name == "vision" then ''
      runHook preBuild
      node --check application/interface/exports.js
      node --check application/interface/pont.js
      python application/interface/compiler.py --style "$PWD/style" --elm ${elmPackages.elm}/bin/elm --elm-format ${elmPackages.elm-format}/bin/elm-format
      runHook postBuild
    '' else ''
      runHook preBuild
      mkdir -p application/.dependances
      cp -R style application/.dependances/style-mrjam
      cd application
      node --check pont.js
      elm make src/Main.elm --optimize --output=elm.js
      mkdir site
      cp index.html pont.js elm.js site/
      for resource in ${lib.concatMapStringsSep " " lib.escapeShellArg lock.frontends.${name}.style_public_files}; do
        install -Dm644 "../style/public/$resource" "site/$resource"
      done
      cp -R ${inputs}/resources/${name}/. site/
      runHook postBuild
    '';
    installPhase = ''
      runHook preInstall
      mkdir -p "$out/share/mrjam/${name}"
      cp -R ${if name == "vision" then "application/interface/dist" else "site"}/. "$out/share/mrjam/${name}/"
      runHook postInstall
    '';
    postFixup = ''
      python ${support}/check_frontend_site.py --site "$out/share/mrjam/${name}"
      python ${support}/frontend_artifact.py --output "$out" --inputs ${inputs} --frontend ${name}
    '';
    meta.platforms = [ "x86_64-linux" ];
  };
in
assert lib.assertMsg (builtins.hashFile "sha256" (inputs + "/materialization.json") == expectedManifestSha256)
  "Frontend inputs differ from the reviewed content hash.";
assert lib.assertMsg (elmPackages.elm.version == "0.19.1") "Elm compiler pin must be preserved.";
assert lib.assertMsg (elmPackages.elm-format.version == "0.8.8") "Vision formatter pin must be preserved.";
{
  vision = frontend "vision";
  log = frontend "log";
  audition = frontend "audition";
}
