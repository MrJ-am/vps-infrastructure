{ lib, runCommand, python3, makeWrapper, openssl, writeText
, authorityPolicy, producerBinding
}:
let
  policy = writeText "mrjam-validation-authority-policy.json" (builtins.toJSON authorityPolicy);
  exportPolicy = writeText "mrjam-validation-export-policy.json" (builtins.toJSON {
    schema_version = 1;
    rules_revision = authorityPolicy.rules_revision;
    requester_uid = authorityPolicy.signer_uid;
    producer = producerBinding;
  });
in
assert authorityPolicy.producer == producerBinding;
runCommand "mrjam-validation-authority-1" {
  nativeBuildInputs = [ python3 makeWrapper ];
  passthru = { inherit policy exportPolicy producerBinding; };
} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${./contract.py} "$out/lib/contract.py"
  cp ${./producer.py} "$out/lib/producer.py"
  cp ${./collector.py} "$out/lib/collector.py"
  cp ${./exporter.py} "$out/lib/exporter.py"
  cp ${./signer.py} "$out/lib/signer.py"
  cp ${./client.py} "$out/lib/client.py"
  cp ${../../forgejo/worker.py} "$out/lib/frozen_worker.py"
  substituteInPlace "$out/lib/exporter.py" --replace-fail '@export-policy@' '${exportPolicy}'
  substituteInPlace "$out/lib/signer.py" \
    --replace-fail '@authority-policy@' '${policy}' \
    --replace-fail '@openssl@' '${openssl}/bin/openssl'
  substituteInPlace "$out/lib/client.py" --replace-fail '@authority-policy@' '${policy}'
  ${python3}/bin/python3 -I -S - "$out/lib" '${policy}' <<'PY'
  import ast,json,pathlib,sys
  root=pathlib.Path(sys.argv[1])
  for file in root.glob('*.py'): ast.parse(file.read_bytes())
  sys.path.insert(0,str(root))
  import contract
  contract.policy(json.loads(pathlib.Path(sys.argv[2]).read_bytes()))
  PY
  for pair in 'mrjam-validation-bound-worker producer' 'mrjam-validation-bound-collector collector' 'mrjam-validation-export exporter' 'mrjam-validation-attest signer' 'mrjam-validation-request-attestation client'; do
    set -- $pair
    makeWrapper ${python3}/bin/python3 "$out/bin/$1" --add-flags '-I -S' --add-flags "$out/lib/$2.py"
  done
''
