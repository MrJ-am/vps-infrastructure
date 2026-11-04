# Qualification only: no host module, credentials, production data or deployment.
{ pkgs ? import /nix/store/ydk30pf7qngrw0ws113m9p005p681rxy-source {}
, source ? ../../../.local/deployment-20261101/platform-aligned-workspace-001
}:
let
  rust = (pkgs.symlinkJoin {
    name = "mrjam-alignment-rust-toolchain-1.99.1";
    paths = [ (builtins.storePath /nix/store/2va2x1g4ncjhaih1dk0zxvi97s832pw9-mrjam-rust-toolchain-1.99.1) ];
  }) // { version = "1.99.1"; };
  platform = pkgs.makeRustPlatform {
    cargo = rust;
    rustc = rust // { targetPlatforms = [ "x86_64-linux" ]; badTargetPlatforms = []; };
  };
  pg = pkgs.postgresql_17.withPackages (p: [ p.pgvector ]);
in platform.buildRustPackage {
  pname = "mrjam-aligned-workspace";
  version = "673d9b6befe2";
  src = source;
  cargoLock.lockFile = source + "/Cargo.lock";
  nativeBuildInputs = [ pkgs.pkg-config pkgs.openssl pg ];
  buildInputs = [ pkgs.sqlite ];
  strictDeps = true;
  CARGO_BUILD_JOBS = "2";
  cargoBuildFlags = [ "--workspace" ];
  cargoTestFlags = [ "--workspace" "--all-features" ];
  checkFlags = [ "--test-threads=1" ];
  preBuild = ''
    cargo fmt --all --check
  '';
  preCheck = ''
    test "$(id -u)" != 0
    initdb -D "$TMPDIR/pg" --username=mrjam_synthetic --auth-local=trust --auth-host=trust --encoding=UTF8 --locale=C > /dev/null
    pg_ctl -D "$TMPDIR/pg" -l "$TMPDIR/pg-output" -o "-c listen_addresses=127.0.0.1 -p 55432 -c unix_socket_directories=$TMPDIR -c max_connections=32 -c shared_buffers=32MB -c log_statement=none" -w start > /dev/null
    trap 'pg_ctl -D "$TMPDIR/pg" -m immediate -w stop > /dev/null' EXIT
    createdb -h 127.0.0.1 -p 55432 -U mrjam_synthetic mrjam_synthetic
    export MRJAM_SYNTHETIC_DATABASE_URL=postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic
    export VISION_TEST_ADMIN_URL="$MRJAM_SYNTHETIC_DATABASE_URL"
  '';
  postCheck = ''
    cargo clippy --workspace --all-targets --all-features --release --frozen --offline -- -D warnings -F unsafe_code
  '';
  doCheck = true;
  meta.platforms = [ "x86_64-linux" ];
}
