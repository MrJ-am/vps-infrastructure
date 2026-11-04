{ pkgs }:
pkgs.runCommand "mrjam-validation-authority-key-bootstrap-1" { nativeBuildInputs = [ pkgs.makeWrapper ]; } ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${./bootstrap.py} "$out/lib/bootstrap.py"
  substituteInPlace "$out/lib/bootstrap.py" --replace-fail '@openssl@' '${pkgs.openssl}/bin/openssl'
  ${pkgs.python3}/bin/python3 -I -S -c 'import ast,sys;ast.parse(open(sys.argv[1]).read())' "$out/lib/bootstrap.py"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-validation-authority-key-bootstrap" \
    --add-flags '-I -S' --add-flags "$out/lib/bootstrap.py"
''
