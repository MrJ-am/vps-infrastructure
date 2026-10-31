{ lib, stdenvNoCC, python3, makeWrapper }:
stdenvNoCC.mkDerivation {
  pname = "mrjam-admission-adoption";
  version = "1";
  # An exact file set excludes local __pycache__ directories as well as their
  # contents, so a workspace build and the Git flake select identical inputs.
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./adopt.py ./test_adopt.py ./schema-provenance.json
      ./schemas/legacy-requests.sql ./schemas/legacy-mail.sql
      ./schemas/target-requests.sql ./schemas/target-mail.sql
    ];
  };
  nativeBuildInputs = [ python3 makeWrapper ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    ${python3}/bin/python3 -I -S -m unittest discover -s . -p test_adopt.py -v
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    install -Dm644 adopt.py "$out/libexec/adopt.py"
    install -Dm644 schema-provenance.json "$out/libexec/schema-provenance.json"
    mkdir -p "$out/libexec/schemas" "$out/bin"
    install -m644 schemas/*.sql "$out/libexec/schemas/"
    makeWrapper ${python3}/bin/python3 "$out/bin/mrjam-admission-adopt" \
      --add-flags "-I -S $out/libexec/adopt.py"
    runHook postInstall
  '';
  meta.platforms = [ "x86_64-linux" ];
}
