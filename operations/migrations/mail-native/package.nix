{ lib, stdenvNoCC, python3, makeWrapper }:
stdenvNoCC.mkDerivation {
  pname = "mrjam-mail-native-adoption";
  version = "2";
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./adopt.py ./test_adopt.py ./schema-provenance.json
      ./schemas/legacy-mail.sql ./schemas/native-mail.sql ./schemas/target-mail.sql
      ./schemas/cycle-markers.sql ./schemas/closure-markers.sql
    ];
  };
  nativeBuildInputs = [ python3 makeWrapper ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    ${python3}/bin/python3 -I -S -m unittest discover -s . -p 'test_*.py' -v
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/libexec/schemas" "$out/bin"
    install -m644 schemas/*.sql "$out/libexec/schemas/"
    install -m644 schema-provenance.json "$out/libexec/schema-provenance.json"
    for profile in cycle archive; do
      install -m644 adopt.py "$out/libexec/adopt-$profile.py"
      substituteInPlace "$out/libexec/adopt-$profile.py" \
        --replace-fail 'PROFILE = None' "PROFILE = '$profile'"
      makeWrapper ${python3}/bin/python3 "$out/bin/mrjam-$profile-mail-adopt" \
        --add-flags "-I -S $out/libexec/adopt-$profile.py"
    done
    runHook postInstall
  '';
  meta.platforms = [ "x86_64-linux" ];
}
