# Protected package factory shared by deployment and the synthetic IPC fixture.
# Arguments belong to the installed control recipe, never to candidate input.
{ pkgs, policy, producer, worker, details, bindings, bubblewrap, expectedSteps
, profile ? "platform", extraAnchors ? {}, viseRules ? null }:
assert builtins.elem profile ["platform" "vise-v1"];
assert builtins.all (name: builtins.elem name ["platform" "vise-v1"] && name!=profile)
  (builtins.attrNames extraAnchors);
let
  rules=if viseRules==null then null else builtins.path {path=viseRules;name="mrjam-installed-vise-rules";};
  rulesExport=if rules==null then null else builtins.fromJSON (builtins.readFile (rules+"/export.json"));
  visePolicy=if profile=="vise-v1" then policy else
    if extraAnchors ? vise-v1 then builtins.fromJSON (builtins.readFile extraAnchors.vise-v1) else null;
  rulesBinding=if rules==null then null else pkgs.writeText "mrjam-installed-vise-rules.json" (builtins.toJSON {
    schema_version=1;profile="vise-v1";source=rules;rules_revision=rulesExport.revision;
  });
  rule=name: if rules==null then ../../vise/delivery + "/${name}" else rules+"/delivery/${name}";
  metadataDocuments=[details.runtime details.report_policy]
    ++ pkgs.lib.optional (profile=="platform") details.overlay_manifest;
  profileModules=pkgs.lib.optionalString (profile=="vise-v1" || extraAnchors ? vise-v1) ''
    cp ${rule "authority_profile.py"} "$profileLib/authority_profile.py"
    cp ${rule "source_policy.py"} "$profileLib/source_policy.py"
    cp ${rule "source_scope.py"} "$profileLib/source_scope.py"
  '';
  values={authority=policy; inherit producer worker details;};
  # These are document identifiers, not runtime dependencies of the signing
  # authority or its client. The worker's closure is rooted separately.
  files=pkgs.lib.mapAttrs (name: value: pkgs.writeText ("mrjam-admitted-"+name+".json")
    (builtins.unsafeDiscardStringContext (builtins.toJSON value))) values;
  record={schema_version=1;proposal_sha256=bindings.proposal;
    files=pkgs.lib.mapAttrs (name: value: {path=toString files.${name};sha256=builtins.hashString "sha256" (builtins.toJSON value);}) values;
  };
  recordFile=pkgs.writeText "mrjam-initial-admission.json" (builtins.toJSON record);
  # Public identifiers only, just like files above. The authority/coordinator
  # must not acquire the validator's build/runtime closure through metadata.
  hostBinding=pkgs.writeText "mrjam-authority-host-binding.json" (builtins.unsafeDiscardStringContext (builtins.toJSON {
    schema_version=1;inherit policy producer;
  }));
  metadataSeed=pkgs.runCommand "mrjam-admission-public-metadata" {
    nativeBuildInputs=[pkgs.python3];
    inherit metadataDocuments;
  } ''
    mkdir "$out"
    cp ${../authority-v1/contract.py} contract.py
    cp ${./admission_registry.py} admission_registry.py
    profileLib="$PWD"
    ${profileModules}
    python3 -I -S - "$PWD" "$out" '${recordFile}' '${files.authority}' '${bubblewrap}' '${bindings.closure}' <<'PY'
    import pathlib,sys
    sys.path.insert(0,sys.argv[1]);import contract as C,admission_registry as R
    record=C.parse(pathlib.Path(sys.argv[3]).read_bytes());anchor=C.parse(pathlib.Path(sys.argv[4]).read_bytes())
    captured={}
    def read(path,maximum=131072):
        raw=pathlib.Path(path).read_bytes();assert 0<len(raw)<=maximum
        captured[path]=raw;return raw
    R.resolve(record,record['proposal_sha256'],anchor,sys.argv[5],read=read,now=anchor['not_before']+1,profile='${profile}')
    assert len(captured)==${if profile=="platform" then "8" else "7"}
    for path,raw in captured.items():
        destination=pathlib.Path(sys.argv[2],C.sha(path.encode())+'.data')
        destination.write_bytes(raw);destination.chmod(0o444)
    PY
  '';
  exportAnchor=pkgs.writeText "mrjam-admission-export-anchor.json" (builtins.unsafeDiscardStringContext (builtins.toJSON {
    schema_version=1;rules_revision=policy.rules_revision;
    requester_uid=policy.signer_uid;inherit producer;
  }));
in assert rules==null || (visePolicy!=null && rulesExport.repository=="MrJ-am/mrjam-validation"
  && rulesExport.revision==visePolicy.rules_revision
  && rulesExport.revision!="0000000000000000000000000000000000000000");
pkgs.runCommand "mrjam-validation-admission-control-1" {
  nativeBuildInputs=[pkgs.python3 pkgs.makeWrapper];
  disallowedRequisites=[bindings.validator];
  inherit metadataDocuments;
  passthru={inherit policy producer worker details files recordFile bindings metadataSeed profile extraAnchors;
    policyFile=files.authority; producerBinding=producer; exportPolicy=exportAnchor;
  };
} ''
  mkdir -p "$out/lib" "$out/bin"
  # Keep identifiers in their context-free store file: copying their bytes
  # into this output would make Nix discover validator references again.
  ln -s ${hostBinding} "$out/host-binding.json"
  ${pkgs.lib.optionalString (rulesBinding!=null) "cp ${rulesBinding} \"$out/vise-rules.json\""}
  cp ${../authority-v1/contract.py} "$out/lib/contract.py"
  cp ${../../forgejo/worker.py} "$out/lib/frozen_worker.py"
  cp ${../authority-credentials-v2/reader.py} "$out/lib/signing_credential.py"
  cp ${./admission_registry.py} "$out/lib/admission_registry.py"
  cp ${./admission_control.py} "$out/lib/admission_control.py"
  profileLib="$out/lib"
  ${profileModules}
  cp ${./admission_producer.py} "$out/lib/producer.py"
  cp ${./admission_collector.py} "$out/lib/collector.py"
  cp ${./admission_exporter.py} "$out/lib/exporter.py"
  cp ${./admission_signer.py} "$out/lib/signer.py"
  cp ${./admission_client.py} "$out/lib/client.py"
  substituteInPlace "$out/lib/admission_control.py" \
    --replace-fail '@admission-anchor@' '${files.authority}' \
    --replace-fail '@admission-bubblewrap@' '${bubblewrap}' \
    --replace-fail "PROFILE='platform'" "PROFILE='${profile}'" \
    --replace-fail 'EXTRA_ANCHORS={}' 'EXTRA_ANCHORS=${builtins.toJSON extraAnchors}'
  substituteInPlace "$out/lib/signer.py" "$out/lib/client.py" \
    --replace-fail '@admission-anchor@' '${files.authority}'
  substituteInPlace "$out/lib/signer.py" \
    --replace-fail '/nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin/bin/openssl' '${pkgs.openssl}/bin/openssl'
  substituteInPlace "$out/lib/exporter.py" \
    --replace-fail '@admission-export-anchor@' '${exportAnchor}'
  python3 -I -S - "$out/lib" '${recordFile}' '${files.authority}' '${bindings.closure}/store-paths' <<'PY'
  import ast,pathlib,sys
  root=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(root))
  for path in root.glob('*.py'):ast.parse(path.read_bytes())
  import contract as C,admission_registry as R,admission_control as A
  record=C.parse(pathlib.Path(sys.argv[2]).read_bytes());anchor=C.parse(pathlib.Path(sys.argv[3]).read_bytes())
  read=lambda path,maximum=131072:pathlib.Path(path).read_bytes()
  selected=R.resolve(record,record['proposal_sha256'],anchor,A.BUBBLEWRAP,read=read,now=anchor['not_before']+1,profile=A.PROFILE)
  assert C.sha(pathlib.Path(sys.argv[4]).read_bytes())==anchor['closure_sha256']
  assert C.sha((root/'producer.py').read_bytes())==anchor['producer']['producer_recipe_sha256']
  assert C.sha((root/'collector.py').read_bytes())==anchor['producer']['collector_recipe_sha256']
  assert len(anchor['required_steps'])==${toString expectedSteps}
  # Nix build namespaces do not expose host root ownership. Check content
  # compatibility here; the installed reader keeps its strict root check.
  from unittest.mock import patch
  with patch.object(R,'store_bytes',read):
      for profile in A.EXTRA_ANCHORS:A.anchor_for(profile)
  PY
  for pair in 'mrjam-validation-bound-worker producer' 'mrjam-validation-bound-collector collector' 'mrjam-validation-export exporter' 'mrjam-validation-attest signer' 'mrjam-validation-request-attestation client'; do
    set -- $pair
    makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/$1" --add-flags "-I -S $out/lib/$2.py"
  done
''
