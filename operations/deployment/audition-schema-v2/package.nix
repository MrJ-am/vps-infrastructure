{ pkgs }:
let source = builtins.path {
  path = ./.;
  name = "mrjam-audition-schema-adoption-sources";
  filter = path: type: type == "directory" || builtins.elem (builtins.baseNameOf path)
    [ "build_sql.py" "source.json" "catalogue.sql" "001-reference.sql" "002-additive.sql" ];
};
in
pkgs.runCommand "mrjam-audition-schema-adoption-2" {
  nativeBuildInputs = [ pkgs.python3 ];
} ''
  ${pkgs.python3}/bin/python3 -I -S ${source}/build_sql.py "$out"
''
