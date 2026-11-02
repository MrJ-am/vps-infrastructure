{ pkgs }:
pkgs.runCommand "mrjam-native-backup-synthetic-qualification" {
  nativeBuildInputs = [ pkgs.python3 pkgs.postgresql_17 pkgs.age pkgs.gnutar pkgs.coreutils ];
} ''
  export LANG=C.UTF-8
  cp ${./native.py} native.py
  cp ${./test_native.py} test_native.py
  python3 test_native.py > test-output 2>&1
  mkdir "$out"
  printf '%s\n' '{"schema_version":1,"groups":14,"passed":true,"synthetic_only":true,"postgresql_restore":true,"sqlite_wal":true,"actual_age_envelope":true,"production_access":false,"kanidm_export_fixture":"invented gzip; real provider export qualified separately","cross_component_atomic":false}' > "$out/result.json"
''
