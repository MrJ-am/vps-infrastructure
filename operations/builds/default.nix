{ lib, stdenv, runCommand, python3, callPackage, elmPackages
, materialized
, expectedManifestSha256
, sourceLock ? ./sources.lock.json
}:
let
  toolchains = callPackage ./toolchains.nix { };
  toolsLock = builtins.fromJSON (builtins.readFile ./toolchains.lock.json);
  support = builtins.path {
    path = ./.;
    name = "mrjam-build-support";
    filter = path: type:
      (type == "directory" && path == toString ./.) ||
      (type == "regular" && builtins.elem (builtins.baseNameOf path) [
        "prepare.py" "verify_inputs.py" "artifact_manifest.py"
        "sources.lock.json" "elm-dependencies.lock.json" "toolchains.lock.json"
      ]);
  };
  inputs = builtins.path { path = materialized; name = "mrjam-pinned-build-inputs"; };
  inputManifest = builtins.fromJSON (builtins.readFile (inputs + "/materialization.json"));
  hasJournalAdoption = builtins.pathExists (inputs + "/platform-source/components/vision/src/bin/vision-journal-adoption.rs");
  # No workspace cache or Git checkout is available from these Nix builders.
  verifiedInputs = runCommand "mrjam-verified-build-inputs" {
    nativeBuildInputs = [ python3 ];
  } ''
    python ${support}/verify_inputs.py --inputs ${inputs} --manifest-sha256 ${lib.escapeShellArg expectedManifestSha256} --source-lock ${sourceLock}
    mkdir -p "$out"
    cp ${inputs}/materialization.json "$out/materialization.json"
  '';
  record = kind: ''
    python ${support}/artifact_manifest.py --output "$out" --inputs ${inputs} --artifact ${kind}
  '';
in
assert lib.assertMsg (builtins.hashFile "sha256" (inputs + "/materialization.json") == expectedManifestSha256)
  "Materialized input manifest differs from the reviewed content hash.";
assert lib.assertMsg (elmPackages.elm.version == toolsLock.elm.version)
  "Elm compiler must preserve the application compiler version.";
rec {
  inherit verifiedInputs;
  rustToolchain = toolchains.rust;
  nodeToolchain = toolchains.node;

  rustServer = stdenv.mkDerivation {
    pname = "mrjam-server-preparation";
    version = "0.1.0-${builtins.substring 0 12 inputManifest.source_commits.platform}";
    outputs = [ "out" ] ++ lib.optional hasJournalAdoption "journal";
    dontUnpack = true;
    nativeBuildInputs = [ toolchains.rust python3 ];
    # Panic/source locations must not keep the entire vendor/source tree alive.
    disallowedReferences = [ inputs ];
    configurePhase = ''
      runHook preConfigure
      test -f ${verifiedInputs}/materialization.json
      cp -R ${inputs}/platform-source source
      chmod -R u+w source
      cd source
      export HOME="$TMPDIR/build-home"
      export CARGO_HOME="$TMPDIR/cargo-home"
      export CARGO_TARGET_DIR="$TMPDIR/cargo-target"
      export CARGO_BUILD_JOBS=2
      mkdir -p "$HOME" "$CARGO_HOME" .cargo
      cat > .cargo/config.toml <<'CONFIG'
      [source.crates-io]
      replace-with = "vendored-sources"
      [source.vendored-sources]
      directory = "${inputs}/cargo-vendor"
      [net]
      offline = true
      CONFIG
      test "$(rustc --version | cut -d' ' -f2)" = '${toolsLock.rust.version}'
      test "$(cargo --version | cut -d' ' -f2)" = '${toolsLock.rust.version}'
      export RUSTFLAGS="--remap-path-prefix=$PWD=mrjam-source --remap-path-prefix=${inputs}=mrjam-dependencies"
      runHook postConfigure
    '';
    buildPhase = ''
      runHook preBuild
      cargo build --release --frozen --offline -p mrjam-server
      ${lib.optionalString hasJournalAdoption "cargo build --release --frozen --offline -p mrjam-vision --features postgres --bin vision-journal-adoption"}
      runHook postBuild
    '';
    doCheck = true;
    checkPhase = ''
      runHook preCheck
      cargo test --workspace --frozen --offline
      runHook postCheck
    '';
    installPhase = ''
      runHook preInstall
      install -Dm755 "$CARGO_TARGET_DIR/release/mrjam-server" "$out/bin/mrjam-server"
      ${lib.optionalString hasJournalAdoption ''install -Dm755 "$CARGO_TARGET_DIR/release/vision-journal-adoption" "$journal/bin/vision-journal-adoption"''}
      runHook postInstall
    '';
    postFixup = record "rust-server" + lib.optionalString hasJournalAdoption ''
      python ${support}/artifact_manifest.py --output "$journal" --inputs ${inputs} --artifact vision-journal-adoption
    '';
    meta.platforms = [ "x86_64-linux" ];
  };
  visionJournalAdoption = if hasJournalAdoption then rustServer.journal else null;

  matevalElm = stdenv.mkDerivation {
    pname = "mrjam-mateval-elm-preparation";
    version = builtins.substring 0 12 inputManifest.source_commits.mateval;
    dontUnpack = true;
    nativeBuildInputs = [ toolchains.node elmPackages.elm python3 ];
    configurePhase = ''
      runHook preConfigure
      test -f ${verifiedInputs}/materialization.json
      cp -R ${inputs}/mateval-frontend frontend
      chmod -R u+w frontend
      cp -R ${inputs}/elm-home "$TMPDIR/elm-home"
      chmod -R u+w "$TMPDIR/elm-home"
      export ELM_HOME="$TMPDIR/elm-home"
      export GHCRTS=-N2
      export STYLE_MRJAM_SOURCE=${inputs}/style-source
      export GITHUB_SHA=${inputManifest.source_commits.mateval}
      export HOME="$TMPDIR/build-home"
      mkdir -p "$HOME" frontend/node_modules/.bin
      ln -s ${elmPackages.elm}/bin/elm frontend/node_modules/.bin/elm
      cd frontend
      test "$(node --version)" = 'v${toolsLock.node.version}'
      test "$(elm --version)" = '${toolsLock.elm.version}'
      runHook postConfigure
    '';
    buildPhase = ''
      runHook preBuild
      node scripts/check-artifacts.mjs
      node scripts/build-elm.cjs
      node scripts/version-assets.cjs
      runHook postBuild
    '';
    installPhase = ''
      runHook preInstall
      mkdir -p "$out/share/mrjam/mateval"
      cp -R site/. "$out/share/mrjam/mateval/"
      runHook postInstall
    '';
    postFixup = record "mateval-elm";
    meta.platforms = [ "x86_64-linux" ];
  };
}
