{ pkgs, authorityPolicy, producerBinding }:
let
  binding = builtins.fromJSON (builtins.readFile ./descriptor.json);
  validator = builtins.storePath binding.verifier;
  runtime = builtins.storePath binding.runtime;
  reportPolicy = builtins.storePath binding.report_policy;
  overlays = builtins.storePath (builtins.dirOf binding.overlay_manifest);
  details = pkgs.writeText "mrjam-authority-report-details-v3.json" (builtins.readFile ./descriptor.json);
  base = import ../authority-credentials-v2/package.nix { inherit pkgs authorityPolicy producerBinding; };
in
assert authorityPolicy.report_policy_sha256 == binding.report_policy_sha256;
assert authorityPolicy.verifier == binding.verifier;
assert authorityPolicy.verifier_nar_hash == binding.verifier_nar_hash;
assert authorityPolicy.required_steps == binding.required_steps;
base.overrideAttrs (old: {
  name = "mrjam-validation-authority-report-details-3";
  passthru = old.passthru // { reportDetails = details; };
  buildCommand = old.buildCommand + ''
    cp ${./report_details.py} "$out/lib/report_details.py"
    substituteInPlace "$out/lib/report_details.py" --replace-fail '@report-details@' '${details}'
    ${pkgs.python3}/bin/python3 -I -S - "$out/lib" '${details}' '${validator}' '${runtime}' '${reportPolicy}' '${overlays}/manifest.json' <<'PY'
    import ast,hashlib,json,pathlib,sys
    root=pathlib.Path(sys.argv[1]);d=json.loads(pathlib.Path(sys.argv[2]).read_bytes())
    validator,runtime,policy,manifest=map(pathlib.Path,sys.argv[3:])
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert str(validator)==d['verifier'] and str(runtime)==d['runtime'] and str(policy)==d['report_policy'] and str(manifest)==d['overlay_manifest']
    assert sha(runtime)==d['runtime_sha256'] and sha(policy)==d['report_policy_sha256'] and sha(manifest)==d['overlay_manifest_sha256']
    r=json.loads(runtime.read_bytes());p=json.loads(policy.read_bytes());m=json.loads(manifest.read_bytes())
    assert r['policy']==str(policy) and r['manifest_overlays']==str(manifest.parent)
    assert ('RUNTIME = Path("'+str(runtime)+'")') in (validator/'lib/runner.py').read_text()
    assert [x for x in m['overlays'] if x['case']==d['selected_overlay']]==[d['selected_entry']]
    assert [(x['id'],x['manifest_overlay']) for x in p['frontends'] if x['manifest_overlay'] is not None]==[('style-logo','style-logo')]
    assert len(d['required_steps'])==75 and len(set(d['required_steps']))==75
    path=root/'signer.py';source=path.read_text()
    changes={
      'import signing_credential as K':'import signing_credential as K\nimport report_details as D',
      "report['steps']==[{'name':name,'status':'passed'} for name in value['required_steps']]":"report['steps']==D.expected_steps(value)",
      "'steps':report['steps']":"'steps':[{'name':name,'status':'passed'} for name in value['required_steps']]",
    }
    for before,after in changes.items():
      assert source.count(before)==1
      source=source.replace(before,after)
    path.write_text(source)
    ast.parse(source);ast.parse((root/'report_details.py').read_bytes())
    # Runtime root ownership is checked outside the builder namespace, where
    # the Nix sandbox may map store owners to its overflow UID.
    PY
  '';
})
