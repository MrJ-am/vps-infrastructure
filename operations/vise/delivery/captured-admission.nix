# Invoked only by protected admission code with its installed anchor path.
# This constructs/verifies public bindings; it does not publish an admission.
{ captureRoot, notBefore, expiresAt, anchorControl
, pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}
}:
let
  installedAnchor=builtins.storePath anchorControl;
  rulesPath=installedAnchor+"/vise-rules.json";
  rules=if builtins.pathExists rulesPath then builtins.fromJSON
    (builtins.unsafeDiscardStringContext (builtins.readFile rulesPath)) else null;
  rulesArgs=if rules==null then {} else {
    rulesSource=builtins.storePath rules.source;rulesRevision=rules.rules_revision;
  };
  capture=builtins.fromJSON (builtins.readFile (captureRoot+"/capture.json"));
  source=builtins.path {path=captureRoot+"/source";name="mrjam-captured-vise-source";};
  policy=builtins.path {path=captureRoot+"/policy.json";name="mrjam-captured-vise-policy.json";};
  bindings=import ./proposal-bindings.nix ({
    inherit pkgs;preparedSource=source;policyFile=policy;proposal=capture.proposal_sha256;
  } // rulesArgs);
  nar=pkgs.runCommand "mrjam-captured-vise-validator-nar" {} ''
    ${pkgs.nix}/bin/nix-hash --type sha256 --base64 ${bindings.validator} > "$out"
  '';
  verifierNarHash="sha256-"+pkgs.lib.removeSuffix "\n" (builtins.readFile nar);
  control=import ./authority-package.nix {
    inherit pkgs verifierNarHash;
    viseRules=if rules==null then null else rulesArgs.rulesSource;
    validator=bindings.validator;runtime=bindings.validator.runtime;
    closure=bindings.closure;proposal=bindings.proposal;
    validity={not_before=notBefore;expires_at=expiresAt;};
  };
  publisher=import ../../ci/continuous-delivery-v1/admission-publication.nix {
    inherit pkgs control;anchorControl=installedAnchor;
  };
  descriptor=pkgs.writeText "mrjam-captured-vise-admission.json" (builtins.toJSON {
    schema_version=1;proposal_sha256=capture.proposal_sha256;
    capture_sha256=builtins.hashFile "sha256" (captureRoot+"/capture.json");
    source=bindings.source;validator=bindings.validator;inherit verifierNarHash control publisher;
    record=control.recordFile;metadata=control.metadataSeed;anchor_control=installedAnchor;
  });
in assert rules==null || (builtins.attrNames rules==["profile" "rules_revision" "schema_version" "source"]
  && rules.schema_version==1 && rules.profile=="vise-v1");
assert capture.independently_verified && !capture.deployment_authorized;
assert builtins.hashFile "sha256" policy == capture.policy_sha256;
pkgs.runCommand "mrjam-captured-vise-admission" {nativeBuildInputs=[pkgs.python3];
  passthru={inherit descriptor bindings control publisher;anchorControl=installedAnchor;};
} ''
  mkdir "$out"
  ln -s ${descriptor} "$out/descriptor.json"
  ln -s ${bindings.source} "$out/source"
  ln -s ${control} "$out/control"
  ln -s ${publisher} "$out/publisher"
  python3 -I -S - <<'PY'
  import pathlib,sys
  from unittest.mock import patch
  sys.path.insert(0,'${installedAnchor}/lib')
  import contract as C,admission_registry as R,admission_control as A
  def content(path,maximum=131072):
      raw=pathlib.Path(path).read_bytes();assert 0<len(raw)<=maximum;return raw
  # Build namespaces remap root. Production publisher retains strict metadata.
  with patch.object(R,'store_bytes',content):anchor=A.anchor_for('vise-v1')
  record=C.parse(content('${control.recordFile}'))
  def read(path,maximum=131072):
      raw=content(path,maximum)
      assert content(str(pathlib.Path('${control.metadataSeed}',C.sha(path.encode())+'.data')),maximum)==raw
      return raw
  selected=R.resolve(record,'${bindings.proposal}',anchor,A.BUBBLEWRAP,read=read,
      now=${toString notBefore}+1,profile='vise-v1')
  assert selected['authority']['not_before']==${toString notBefore}
  assert selected['authority']['expires_at']==${toString expiresAt}
  assert len(list(pathlib.Path('${control.metadataSeed}').iterdir()))==7
  PY
''
