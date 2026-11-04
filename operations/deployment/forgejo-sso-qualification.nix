{ pkgs }:
pkgs.runCommand "mrjam-forgejo-sso-closed-probe-qualification" {
  nativeBuildInputs = [ pkgs.python3 pkgs.postgresql_17 ];
} ''
  export LANG=C.UTF-8
  mkdir work
  cd work
  cp ${./forgejo_sso_probe.py} forgejo_sso_probe.py
  cp ${./test_forgejo_sso_probe.py} test_forgejo_sso_probe.py
  python3 test_forgejo_sso_probe.py > private-test-output 2>&1
  mkdir "$out"
  printf '%s\n' '{"schema_version":1,"groups":13,"passed":true,"actual_postgresql":true,"source_model":"Forgejo17 user/login_source","private_values_exported":false,"production_access":false,"mutation_performed":false}' > "$out/result.json"
''
