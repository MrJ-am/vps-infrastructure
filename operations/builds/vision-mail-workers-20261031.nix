{ nixpkgs, materialized }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  toolchains = pkgs.callPackage ./toolchains.nix { };
  expected = "d8290de12d49ecc797904ff5d0cd6d48bb3aa3fe30e1004d6b5bda1493651196";
  revision = "7d87768bd141ec6a2a41b4ec9f3277639fcba67f";
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
  pname = "mrjam-vision-mail-workers";
  outputs = [ "out" "admission" "archive" "cycle" ];
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
    cargo build --release --features workers --frozen --offline --bin vision-admission --bin vision-archive --bin vision-cycle
    runHook postBuild
  '';
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    # PostgreSQL integration remains the separately recorded 43-test native
    # qualification. This build has no database and does not claim those tests.
    cargo test --release --features workers --frozen --offline
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    install -Dm755 "$CARGO_TARGET_DIR/release/vision-admission" "$admission/bin/vision-admission"
    install -Dm755 "$CARGO_TARGET_DIR/release/vision-archive" "$archive/bin/vision-archive"
    install -Dm755 "$CARGO_TARGET_DIR/release/vision-cycle" "$cycle/bin/vision-cycle"
    for target in "$out" "$admission" "$archive" "$cycle"; do
      mkdir -p "$target"
      cp ${inputs}/manifest.json "$target/source-manifest.json"
    done
    runHook postInstall
  '';
  postFixup = ''
    python - "$out" "$admission" "$archive" "$cycle" <<'PYTHON'
    import hashlib,json,pathlib,sys
    catalog={}
    for name,path in zip(("admission","archive","cycle"),sys.argv[2:]):
        root=pathlib.Path(path)
        binary="bin/vision-"+name
        record={"schema_version":1,"artifact":"vision-"+name,"source_commit":"${revision}",
                "input_manifest_sha256":"${expected}","deployment_authorized":False,
                "payload_sha256":{binary:hashlib.sha256((root/binary).read_bytes()).hexdigest()}}
        (root/"artifact.json").write_text(json.dumps(record,sort_keys=True)+"\n")
        catalog[name]={"output":path,"artifact":record}
    (pathlib.Path(sys.argv[1])/"artifacts.json").write_text(json.dumps(catalog,sort_keys=True)+"\n")
    PYTHON
  '';
  meta.platforms = [ "x86_64-linux" ];
}
