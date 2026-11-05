{ source, revision, pkgs ? import ../forgejo/locked-toolchain.nix { } }:
let
  tools = pkgs.callPackage ../builds/toolchains.nix { };
  rust = pkgs.makeRustPlatform {
    cargo = tools.rust;
    rustc = pkgs.rustc // tools.rust;
  };
  postgres = pkgs.postgresql_17.withPackages (ps: [ ps.pgvector ]);
  workspace = builtins.path { path = source + "/serveur"; name = "source"; };
  server = rust.buildRustPackage {
  pname = "mrjam-server";
  version = "0.1.0";
  src = workspace;
  cargoLock.lockFile = workspace + "/Cargo.lock";
  nativeBuildInputs = [ pkgs.pkg-config tools.rust postgres pkgs.python3 pkgs.openssl ];
  buildInputs = [ pkgs.sqlite ];
  cargoBuildFlags = [ "--workspace" ];
  enableParallelBuilding = true;
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    export CARGO_BUILD_JOBS=2
    export CARGO_BUILD_TARGET=x86_64-unknown-linux-gnu
    cargo fmt --all -- --check
    cargo clippy --release --workspace --all-targets --all-features --frozen --offline -- -D warnings
    fixture_database="$TMPDIR/postgres"
    initdb -D "$fixture_database" --username=mrjam_synthetic --auth=trust > "$TMPDIR/initdb.log"
    pg_ctl -D "$fixture_database" -l "$TMPDIR/postgres.log" -o "-h 127.0.0.1 -p 55432 -k $TMPDIR" start
    trap 'pg_ctl -D "$TMPDIR/postgres" -m immediate stop >/dev/null 2>&1 || true' EXIT
    createdb -h 127.0.0.1 -p 55432 -U mrjam_synthetic mrjam_synthetic
    psql -h 127.0.0.1 -p 55432 -U mrjam_synthetic -d mrjam_synthetic -c 'CREATE EXTENSION vector'
    export MRJAM_SYNTHETIC_DATABASE_URL='postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic'
    export VISION_TEST_ADMIN_URL="$MRJAM_SYNTHETIC_DATABASE_URL"
    # Test binaries do not need production LTO. Keep every test and feature,
    # while avoiding repeated expensive LTO links for the integration harnesses.
    export CARGO_PROFILE_TEST_DEBUG=0
    export CARGO_PROFILE_TEST_OPT_LEVEL=2
    cargo test --workspace --all-features --frozen --offline -- --test-threads=1
    pg_ctl -D "$fixture_database" -m fast stop
    trap - EXIT
    runHook postCheck
  '';
  };
  deliveryChecks = pkgs.runCommand "mrjam-delivery-checks" { nativeBuildInputs = [ pkgs.python3 pkgs.nginx ]; } ''
    cd ${source}/operations/continuous-delivery
    export NGINX_TEST_BINARY=${pkgs.nginx}/bin/nginx
    python3 -B -m unittest discover -v
    touch "$out"
  '';
in pkgs.runCommand "mrjam-server-${builtins.substring 0 12 revision}" { } ''
  test -e ${deliveryChecks}
  mkdir -p "$out/bin" "$out/share/mrjam"
  for executable in mrjam-server mrjam-identity mrjam-identity-deletion; do
    test -x ${server}/bin/$executable
    ln -s ${server}/bin/$executable "$out/bin/$executable"
  done
  printf '%s\n' '${revision}' > "$out/share/mrjam/source-revision"
''
