# Independent ViSe application. No shared platform styles, SSO or deployment.
{ nixpkgs, materialized, expectedManifestSha256, sourceLock ? ./sources.lock.json }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  tools = pkgs.callPackage ../builds/toolchains.nix { };
  lock = builtins.fromJSON (builtins.readFile sourceLock);
  inputs = builtins.path { path = materialized; name = "vise-pinned-build-inputs"; };
in
assert builtins.hashFile "sha256" (inputs + "/materialization.json") == expectedManifestSha256;
pkgs.stdenv.mkDerivation {
  pname = "mrjam-vise";
  version = "0.2.0-${builtins.substring 0 12 lock.revision}";
  outputs = [ "out" "tests" ];
  dontUnpack = true;
  nativeBuildInputs = [ tools.rust tools.node pkgs.elmPackages.elm pkgs.python3 ];
  disallowedReferences = [ inputs ];
  configurePhase = ''
    runHook preConfigure
    python ${./verify_inputs.py} --inputs ${inputs} \
      --manifest-sha256 ${pkgs.lib.escapeShellArg expectedManifestSha256} --source-lock ${sourceLock}
    cp -R ${inputs}/source source
    chmod -R u+w source
    cp -R ${inputs}/node_modules source/node_modules
    cp -R ${inputs}/elm-home "$TMPDIR/vise-elm-home"
    chmod -R u+w source "$TMPDIR/vise-elm-home"
    cd source
    export CARGO_HOME="$TMPDIR/vise-cargo-home"
    export CARGO_TARGET_DIR="$TMPDIR/vise-target"
    export CARGO_BUILD_JOBS=2
    export ELM_HOME="$TMPDIR/vise-elm-home"
    export GHCRTS=-N2
    export CARNET_DEMO_ONLY=false
    mkdir -p "$CARGO_HOME" .cargo
    cat > .cargo/config.toml <<'CONFIG'
    [source.crates-io]
    replace-with = "vendored-sources"
    [source.vendored-sources]
    directory = "${inputs}/cargo-vendor"
    [net]
    offline = true
    CONFIG
    export RUSTFLAGS="--remap-path-prefix=$PWD=vise-source --remap-path-prefix=${inputs}=vise-dependencies"
    # Keep compiler 0.19.1 while avoiding an npm lifecycle download.
    rm node_modules/.bin/elm
    ln -s ${pkgs.elmPackages.elm}/bin/elm node_modules/.bin/elm
    test "$(rustc --version | cut -d' ' -f2)" = 1.99.1
    test "$(node --version)" = v24.19.0
    test "$(elm --version)" = 0.19.1
    runHook postConfigure
  '';
  buildPhase = ''
    runHook preBuild
    cargo build --release --frozen --offline --manifest-path backend/Cargo.toml
    node scripts/build.mjs
    mkdir -p "$tests"
    node --input-type=module -e 'import {buildSync} from "esbuild"; buildSync({entryPoints:["tests/api.test.ts"],bundle:true,platform:"node",format:"esm",outfile:process.env.tests+"/api-tests.mjs"});'
    runHook postBuild
  '';
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    node node_modules/typescript/bin/tsc --noEmit
    node --import tsx --test tests/crypto.test.ts tests/contenu.test.ts tests/image.test.ts tests/poll.test.ts
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    install -Dm755 "$CARGO_TARGET_DIR/release/etp-carnet-server" "$out/server"
    cp -R dist "$out/dist"
    install -Dm644 LICENSE "$out/share/licenses/vise/LICENSE"
    install -Dm644 COPYING "$out/share/licenses/vise/COPYING"
    runHook postInstall
  '';
  postFixup = ''
    python ${./record_artifact.py} "$out" ${pkgs.lib.escapeShellArg lock.revision} ${pkgs.lib.escapeShellArg expectedManifestSha256}
  '';
  meta = {
    platforms = [ "x86_64-linux" ];
    license = pkgs.lib.licenses.lgpl3Plus;
    description = "Independent encrypted ViSe notebook, pinned Rust/Elm build";
  };
}
