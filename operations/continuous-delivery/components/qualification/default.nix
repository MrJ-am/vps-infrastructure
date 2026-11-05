# Standalone tests only; no CI registration, activation or deployment.
{ source, pkgs ? import ../../../forgejo/locked-toolchain.nix {} }:
let
  fixtureProgram = import (source + "/operations/continuous-delivery/migration-test-program.nix") {inherit pkgs;};
  support = builtins.path {
    path = ./.;
    name = "independent-delivery-test-support";
    filter = path: type:
      (type == "directory" && path == toString ./.) ||
      (type == "regular" && pkgs.lib.hasSuffix "_cases.py" (builtins.baseNameOf path));
  };
in pkgs.runCommand "mrjam-independent-delivery-qualification" {
  nativeBuildInputs = [pkgs.python3 pkgs.postgresql_17 pkgs.nginx];
} ''
  export HOME="$TMPDIR/home"
  mkdir -p "$HOME"
  initdb -D "$TMPDIR/postgres" -U mrjam_synthetic -A trust --encoding=UTF8 >/dev/null
  pg_ctl -D "$TMPDIR/postgres" -l "$TMPDIR/postgres.log" -o "-h 127.0.0.1 -p 55432 -k $TMPDIR" -w start
  trap 'pg_ctl -D "$TMPDIR/postgres" -m immediate stop >/dev/null 2>&1 || true' EXIT
  createdb -h 127.0.0.1 -p 55432 -U mrjam_synthetic mrjam_synthetic
  export MRJAM_SYNTHETIC_DATABASE_URL='postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic'
  export SOURCE_ROOT=${source}
  export MRJAM_TEST_MIGRATION_PROGRAM=${fixtureProgram}
  export PYTHONDONTWRITEBYTECODE=1
  python3 -B -m unittest discover -s ${support} -p '*_cases.py' -v
  pg_ctl -D "$TMPDIR/postgres" -m fast -w stop
  trap - EXIT
  touch "$out"
''
