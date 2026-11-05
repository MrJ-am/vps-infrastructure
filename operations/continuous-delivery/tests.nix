{ source, pkgs ? import ../forgejo/locked-toolchain.nix { }, server ? null,
  runtime ? null, migrationPlan ? null, previousServer ? null,
  postgres ? pkgs.postgresql_17.withPackages (ps: [ ps.pgvector ]) }:
let
  program = import ./migration-test-program.nix { inherit pkgs; };
in pkgs.runCommand "mrjam-system-delivery-checks" {
  nativeBuildInputs = [ pkgs.python3 pkgs.nginx postgres ];
} ''
  export HOME="$TMPDIR/home"
  mkdir -p "$HOME"
  initdb -D "$TMPDIR/pg" --username=mrjam_synthetic --auth=trust > /dev/null
  pg_ctl -D "$TMPDIR/pg" -l "$TMPDIR/pg.log" -o "-h 127.0.0.1 -p 55432 -k $TMPDIR" start
  trap 'pg_ctl -D "$TMPDIR/pg" -m immediate stop >/dev/null 2>&1 || true' EXIT
  createdb -h 127.0.0.1 -p 55432 -U mrjam_synthetic mrjam_synthetic
  export MRJAM_SYNTHETIC_DATABASE_URL='postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic'
  export MRJAM_TEST_MIGRATION_PROGRAM=${program}
  export NGINX_TEST_BINARY=${pkgs.nginx}/bin/nginx
  export PYTHONDONTWRITEBYTECODE=1
  ${pkgs.lib.optionalString (server != null) ''
    export MRJAM_PREVIOUS_SERVER=${if previousServer == null then server else builtins.storePath previousServer}/bin/mrjam-server
    export MRJAM_CANDIDATE_SERVER=${server}/bin/mrjam-server
  ''}
  cd ${source}/operations/continuous-delivery
  python3 -B -m unittest discover -v
  python3 -B -m unittest discover -s components -p test_components.py -v
  export SOURCE_ROOT=${source}
  python3 -B -m unittest discover -s components/qualification -p '*_cases.py' -v
  ${pkgs.lib.optionalString (migrationPlan != null) ''
    python3 -B check_plan.py ${migrationPlan} ${postgres}/bin/psql
  ''}
  ${pkgs.lib.optionalString (runtime != null && server != null) ''
    python3 -B check_assets.py ${server}/bin/mrjam-server ${runtime}/runtime.json
  ''}
  pg_ctl -D "$TMPDIR/pg" -m fast stop
  trap - EXIT
  touch "$out"
''
