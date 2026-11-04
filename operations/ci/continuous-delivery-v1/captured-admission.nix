# Only a protected capture directory is accepted by the controller calling this
# fixed expression. No Nix file from the candidate is imported or evaluated.
{ captureRoot, notBefore, expiresAt
, pkgs ? import ../../forgejo/locked-toolchain.nix {}
, anchorControl ? "/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1"
}:
let
  capture=builtins.fromJSON (builtins.readFile (captureRoot+"/capture.json"));
  source=builtins.path {path=captureRoot+"/source";name="mrjam-captured-source";};
  policy=builtins.path {path=captureRoot+"/policy.json";name="mrjam-captured-policy.json";};
  bindings=import ./proposal-bindings.nix {
    inherit pkgs;preparedSource=source;policyFile=policy;proposal=capture.proposal_sha256;
  };
  nar=pkgs.runCommand "mrjam-captured-validator-nar" {} ''
    ${pkgs.nix}/bin/nix-hash --type sha256 --base64 ${bindings.validator} > "$out"
  '';
  verifierNarHash="sha256-"+pkgs.lib.removeSuffix "\n" (builtins.readFile nar);
  control=import ./admission-package.nix {
    inherit pkgs bindings verifierNarHash;
    retainOverlay=true;
    validity={not_before=notBefore;expires_at=expiresAt;};
  };
  installedAnchor=builtins.storePath anchorControl;
  publisher=import ./admission-publication.nix {inherit pkgs control;anchorControl=installedAnchor;};
  descriptor=pkgs.writeText "mrjam-captured-admission.json" (builtins.toJSON {
    schema_version=1;proposal_sha256=capture.proposal_sha256;
    capture_sha256=builtins.hashFile "sha256" (captureRoot+"/capture.json");
    source=bindings.source;validator=bindings.validator;inherit verifierNarHash control publisher;
    record=control.recordFile;metadata=control.metadataSeed;anchor_control=installedAnchor;
  });
in assert capture.independently_verified && !capture.deployment_authorized;
assert builtins.hashFile "sha256" policy == capture.policy_sha256;
pkgs.runCommand "mrjam-captured-admission" {nativeBuildInputs=[pkgs.python3];
  passthru={inherit descriptor bindings control publisher;anchorControl=installedAnchor;};
} ''
  mkdir "$out"
  ln -s ${descriptor} "$out/descriptor.json"
  ln -s ${bindings.source} "$out/source"
  ln -s ${control} "$out/control"
  ln -s ${publisher} "$out/publisher"
  python3 -I -S - <<'PY'
  import json,pathlib,sys
  sys.path.insert(0,'${installedAnchor}/lib')
  import contract as C,admission_registry as R,admission_control as A
  record=C.parse(pathlib.Path('${control.recordFile}').read_bytes())
  anchor=C.parse(pathlib.Path(A.ANCHOR_PATH).read_bytes())
  def read(path,maximum=131072):
      raw=pathlib.Path(path).read_bytes();assert 0<len(raw)<=maximum
      assert pathlib.Path('${control.metadataSeed}',C.sha(path.encode())+'.data').read_bytes()==raw
      return raw
  # Qualification against the installed anchor, never the new record itself.
  selected=R.resolve(record,'${bindings.proposal}',anchor,A.BUBBLEWRAP,read=read,now=${toString notBefore}+1)
  assert selected['authority']['not_before']==${toString notBefore}
  assert selected['authority']['expires_at']==${toString expiresAt}
  assert len(list(pathlib.Path('${control.metadataSeed}').iterdir()))==8
  PY
''
