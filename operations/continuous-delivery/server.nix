{ source, revision, pkgs ? import ../forgejo/locked-toolchain.nix { } }:
let
  tools = pkgs.callPackage ../builds/toolchains.nix { };
  rust = pkgs.makeRustPlatform {
    cargo = tools.rust;
    rustc = pkgs.rustc // tools.rust;
  };
  postgres = pkgs.postgresql_17.withPackages (ps: [ ps.pgvector ]);
in rust.buildRustPackage {
  pname = "mrjam-server";
  version = builtins.substring 0 12 revision;
  src = source;
  sourceRoot = "source/serveur";
  cargoLock.lockFile = source + "/serveur/Cargo.lock";
  nativeBuildInputs = [ pkgs.pkg-config tools.rust postgres pkgs.python3 ];
  buildInputs = [ pkgs.sqlite ];
  cargoBuildFlags = [ "-p" "mrjam-server" ];
  enableParallelBuilding = true;
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    export CARGO_BUILD_JOBS=2
    cargo fmt --all -- --check
    cargo clippy --release --workspace --all-targets --all-features --frozen --offline -- -D warnings
    export PGDATA="$TMPDIR/postgres"
    initdb --username=mrjam_synthetic --auth=trust > "$TMPDIR/initdb.log"
    pg_ctl -l "$TMPDIR/postgres.log" -o "-h 127.0.0.1 -p 55432 -k $TMPDIR" start
    trap 'pg_ctl -m immediate stop >/dev/null 2>&1 || true' EXIT
    createdb -h 127.0.0.1 -p 55432 -U mrjam_synthetic mrjam_synthetic
    psql -h 127.0.0.1 -p 55432 -U mrjam_synthetic -d mrjam_synthetic -c 'CREATE EXTENSION vector'
    export MRJAM_SYNTHETIC_DATABASE_URL='postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic'
    export VISION_TEST_ADMIN_URL="$MRJAM_SYNTHETIC_DATABASE_URL"
    cargo test --release --workspace --all-features --frozen --offline -- --test-threads=1
    pg_ctl -m fast stop
    trap - EXIT
    runHook postCheck
  '';
  postInstall = ''
    mkdir -p "$out/share/mrjam"
    printf '%s\n' '${revision}' > "$out/share/mrjam/source-revision"
  '';
}
