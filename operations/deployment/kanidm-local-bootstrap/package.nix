{ lib, stdenvNoCC, python3, makeWrapper }:
let provision=builtins.storePath "/nix/store/13qs6kk65vss4k3mcb86aiv8nww1qazl-mrjam-kanidm-worker-provision-3";
in stdenvNoCC.mkDerivation {
  pname="mrjam-kanidm-local-bootstrap";
  version="1";
  src=lib.fileset.toSource {root=./.;fileset=lib.fileset.unions [./bootstrap.py ./builtin_probe.py ./test_builtin_probe.py];};
  nativeBuildInputs=[python3 makeWrapper];
  dontBuild=true;
  doCheck=true;
  checkPhase=''
    ${python3}/bin/python3 -I -m unittest discover -s . -p test_builtin_probe.py -v
    ${python3}/bin/python3 -I -c 'import ast,pathlib;ast.parse(pathlib.Path("bootstrap.py").read_bytes())'
  '';
  installPhase=''
    mkdir -p "$out/libexec" "$out/bin"
    install -m644 bootstrap.py builtin_probe.py "$out/libexec/"
    test -f ${provision}/libexec/provision.py
    makeWrapper ${python3}/bin/python3 "$out/bin/mrjam-kanidm-local-bootstrap" \
      --add-flags "-I -S $out/libexec/bootstrap.py"
  '';
  meta.platforms=["x86_64-linux"];
}
