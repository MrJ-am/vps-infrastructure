{ lib, stdenvNoCC, python3, makeWrapper }:
stdenvNoCC.mkDerivation {
  pname = "mrjam-validation-stage-sources";
  version = "1";
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [ ./stage_sources.py ./worker.py ./tests/test_stage_sources.py ];
  };
  nativeBuildInputs = [ python3 makeWrapper ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    ${python3}/bin/python3 -I -S -m unittest discover -s tests -p test_stage_sources.py -v
  '';
  installPhase = ''
    install -Dm644 stage_sources.py "$out/libexec/stage_sources.py"
    install -Dm644 worker.py "$out/libexec/worker.py"
    mkdir -p "$out/bin"
    makeWrapper ${python3}/bin/python3 "$out/bin/mrjam-validation-stage-sources" \
      --add-flags "-I -S $out/libexec/stage_sources.py"
  '';
  meta.platforms = [ "x86_64-linux" ];
}
