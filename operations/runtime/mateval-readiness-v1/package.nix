{ pkgs ? import /nix/store/ydk30pf7qngrw0ws113m9p005p681rxy-source {}
, workspace ? ../../..
}:
let
  rust = builtins.storePath /nix/store/2va2x1g4ncjhaih1dk0zxvi97s832pw9-mrjam-rust-toolchain-1.99.1;
  inputs = builtins.storePath /nix/store/z0gvz1ynawnkvrrlh2c69x3l255jf0rd-mrjam-pinned-build-inputs;
  proposal = builtins.path {
    path = workspace + "/.local/ci-artifact-recovery-20261102/proposal-base";
    name = "mrjam-reviewed-proposal-8bf05fb9065a";
  };
  source = pkgs.runCommand "mrjam-platform-reviewed-4e65423ceaae" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 -I -S ${./prepare.py} ${proposal} "$out"
  '';
  pg = pkgs.postgresql_17.withPackages (p: [ p.pgvector ]);
in assert builtins.hashFile "sha256" ./readiness.patch == "90d22b2216eb4496d3f518863d1f1ed8f41e524443b0cdd80c2463ea81fc48b4";
pkgs.stdenv.mkDerivation {
  pname = "mrjam-server-mateval-typed-readiness";
  version = "1";
  src = source;
  patches = [ ./readiness.patch ];
  nativeBuildInputs = [ rust pkgs.python3 pkgs.openssl pg ];
  disallowedReferences = [ inputs source proposal rust ];
  configurePhase = ''
    export HOME="$TMPDIR/build-home"
    export CARGO_HOME="$TMPDIR/cargo-home"
    export CARGO_TARGET_DIR="$TMPDIR/cargo-target"
    export CARGO_NET_OFFLINE=true
    export CARGO_BUILD_JOBS=2
    mkdir -p "$HOME" "$CARGO_HOME" .cargo
    cat > .cargo/config.toml <<'CONFIG'
    [source.crates-io]
    replace-with = "reviewed-vendor"
    [source.reviewed-vendor]
    directory = "${inputs}/cargo-vendor"
    [net]
    offline = true
    CONFIG
    export RUSTFLAGS="--remap-path-prefix=$PWD=mrjam-source --remap-path-prefix=${inputs}=mrjam-dependencies"
  '';
  buildPhase = ''
    cargo fmt --all --check
    cargo build --release --frozen --offline -p mrjam-server
  '';
  doCheck = true;
  checkPhase = ''
    test "$(id -u)" != 0
    initdb -D "$TMPDIR/pg" --username=mrjam_synthetic --auth-local=trust --auth-host=trust --encoding=UTF8 --locale=C > /dev/null
    pg_ctl -D "$TMPDIR/pg" -l "$TMPDIR/pg-output" -o "-c listen_addresses=127.0.0.1 -p 55432 -c unix_socket_directories=$TMPDIR -c max_connections=32 -c shared_buffers=32MB -c log_statement=none" -w start > /dev/null
    trap 'pg_ctl -D "$TMPDIR/pg" -m immediate -w stop > /dev/null' EXIT
    createdb -h 127.0.0.1 -p 55432 -U mrjam_synthetic mrjam_synthetic
    export MRJAM_SYNTHETIC_DATABASE_URL=postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic
    export VISION_TEST_ADMIN_URL="$MRJAM_SYNTHETIC_DATABASE_URL"
    cargo test --workspace --all-features --release --frozen --offline -- --test-threads=1
    cargo clippy --workspace --all-targets --all-features --release --frozen --offline -- -D warnings -F unsafe_code
  '';
  installPhase = ''
    install -Dm755 "$CARGO_TARGET_DIR/release/mrjam-server" "$out/bin/mrjam-server"
  '';
  postFixup = ''
    python3 -I -S ${./artifact_manifest.py} "$out" ${./readiness.patch}
  '';
}
