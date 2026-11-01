{ runCommand, python3, postgresql_17, replaceVars }:
let source = replaceVars ./check_adoption.py {
  python = "${python3}/bin/python3";
  psql = "${postgresql_17}/bin/psql";
  contract = "${./schema-contract.json}";
};
in runCommand "mrjam-vise-check-adoption-v1" { } ''
  install -Dm555 ${source} "$out/bin/mrjam-vise-check-adoption"
''
