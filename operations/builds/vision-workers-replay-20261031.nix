{ nixpkgs, materialized }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  toolchains = pkgs.callPackage ./toolchains.nix { };
  expected = "ba585b4e5a4ded40c8f268732f8dbafc6a5581cb162ac833108eca48ced04651";
  revision = "51e7bcd63f4ab36ddadd14fa8cf531e336a076ce";
  inputs = builtins.path { path = materialized; name = "mrjam-vision-workers-inputs"; };
  support = builtins.path {
    path = ./.; name = "mrjam-vision-workers-build-support";
    filter = path: type: (type == "directory" && path == toString ./.) ||
      (type == "regular" && builtins.elem (builtins.baseNameOf path) [ "prepare.py" "prepare_vision_workers.py" ]);
  };
in
assert builtins.hashFile "sha256" (inputs + "/manifest.json") == expected;
assert (builtins.fromJSON (builtins.readFile (inputs + "/manifest.json"))).source_commit == revision;
assert toolchains.rust.version == "1.99.1";
pkgs.stdenv.mkDerivation {
  pname = "mrjam-vision-workers";
  version = "0.1.0-${builtins.substring 0 12 revision}";
  dontUnpack = true;
  nativeBuildInputs = [ toolchains.rust pkgs.python3 pkgs.openssl ];
  disallowedReferences = [ inputs ];
  configurePhase = ''
    runHook preConfigure
    python ${support}/prepare_vision_workers.py verify ${inputs} '${expected}'
    cp -R ${inputs}/source source
    chmod -R u+w source
    cd source
    export CARGO_HOME="$TMPDIR/cargo-home"
    export CARGO_TARGET_DIR="$TMPDIR/cargo-target"
    export CARGO_BUILD_JOBS=1
    export CARGO_INCREMENTAL=0
    mkdir -p "$CARGO_HOME" .cargo
    cat > .cargo/config.toml <<'CONFIG'
    [source.crates-io]
    replace-with = "vendored-sources"
    [source.vendored-sources]
    directory = "${inputs}/cargo-vendor"
    [net]
    offline = true
    CONFIG
    export RUSTFLAGS="--remap-path-prefix=$PWD=mrjam-vision-source --remap-path-prefix=${inputs}=mrjam-dependencies"
    runHook postConfigure
  '';
  buildPhase = ''
    runHook preBuild
    cargo build --release --features workers --frozen --offline --bin vision-archive --bin vision-replay
    runHook postBuild
  '';
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    # PostgreSQL integration remains the separately recorded 35-test native
    # qualification. This build has no database and does not claim those tests.
    cargo test --release --features workers --frozen --offline
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    install -Dm755 "$CARGO_TARGET_DIR/release/vision-archive" "$out/bin/vision-archive"
    install -Dm755 "$CARGO_TARGET_DIR/release/vision-replay" "$out/bin/vision-replay"
    cp ${inputs}/manifest.json "$out/source-manifest.json"
    runHook postInstall
  '';
  postFixup = ''
    python - "$out" <<'PY'
    import hashlib,json,pathlib,sys
    root=pathlib.Path(sys.argv[1])
    record={"schema_version":1,"artifact":"vision-workers","source_commit":"${revision}",
            "input_manifest_sha256":"${expected}","deployment_authorized":False,
            "payload_sha256":{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ("bin/vision-archive","bin/vision-replay")}}
    (root/"artifact.json").write_text(json.dumps(record,sort_keys=True)+"\n")
    PY
  '';
  meta.platforms = [ "x86_64-linux" ];
}
