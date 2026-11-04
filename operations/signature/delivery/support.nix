# Proposed immutable helper; selecting it for production requires rule adoption.
{rulesRoot, pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  python=import ./toolchain.nix {inherit pkgs;};
  files=["consumer_identity.py" "prepare_identity.py" "parisienne.py"
    "verify_generated.py" "reference-generator.py" "generator-provenance.json"];
in pkgs.runCommand "mrjam-signature-verifier-support-1" {
  nativeBuildInputs=[python];passthru={inherit python;};
} ''
  mkdir "$out"
  ${pkgs.lib.concatMapStringsSep "\n" (name: ''
    cp ${rulesRoot+("/workflow-runner/"+name)} "$out/${name}"
  '') files}
  python3 -I - "$out" <<'PY'
  import ast,hashlib,json,pathlib,sys
  root=pathlib.Path(sys.argv[1])
  for source in root.glob('*.py'):ast.parse(source.read_bytes())
  assert hashlib.sha256((root/'reference-generator.py').read_bytes()).hexdigest()==json.loads((root/'generator-provenance.json').read_bytes())['sha256']
  PY
''
