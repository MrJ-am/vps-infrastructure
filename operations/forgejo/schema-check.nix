{ runCommand, replaceVars, python3, postgresql_17 }:
let
  script = replaceVars ./check_schema.py {
    python = "${python3}/bin/python3";
    psql = "${postgresql_17}/bin/psql";
    contract = "${./schema-contract.json}";
  };
in runCommand "mrjam-forgejo-schema-check-17.0.1" { } ''
  mkdir -p "$out/bin"
  cp ${script} "$out/bin/mrjam-forgejo-check-schema"
  chmod 0555 "$out/bin/mrjam-forgejo-check-schema"
''
