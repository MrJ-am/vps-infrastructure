{ lib, stdenvNoCC, python3, makeWrapper, age, journalDatabase ? "vision_journal" }:
assert builtins.match "[a-z][a-z0-9_]{0,62}" journalDatabase != null;
assert !(lib.hasPrefix "pg_" journalDatabase);
assert !(builtins.elem journalDatabase [ "postgres" "template0" "template1" "all" "replication" ]);
stdenvNoCC.mkDerivation {
  pname = "mrjam-worker-credential-adaptation";
  version = "1";
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [ ./adapt.py ./test_adapt.py ./provenance.json ];
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
    install -Dm644 adapt.py "$out/libexec/adapt.py"
    install -m644 provenance.json "$out/libexec/provenance.json"
    cat > "$out/libexec/public.json" <<'JSON'
    ${builtins.toJSON { journal_database = journalDatabase; age_program = "${age}/bin/age"; }}
    JSON
    mkdir -p "$out/bin"
    makeWrapper ${python3}/bin/python3 "$out/bin/mrjam-worker-credentials-adapt" \
      --add-flags "-I -S $out/libexec/adapt.py"
    runHook postInstall
  '';
  meta.platforms = [ "x86_64-linux" ];
}
