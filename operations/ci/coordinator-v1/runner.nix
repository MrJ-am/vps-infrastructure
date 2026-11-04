{ pkgs, authorityPackage }:
let base = pkgs.callPackage ../../forgejo/runner-admission.nix {};
in base.overrideAttrs (old: {
  pname = "mrjam-forgejo-runner-content-authority";
  # The extension uses only standard-library imports and the already vendored
  # x/sys package. go.mod/go.sum are unchanged; reuse their exact fixed output.
  goModules = base.goModules;
  postPatch = (old.postPatch or "") + ''
    cp ${./runner-attestation.go} internal/app/run/mrjam_attestation.go
    cp ${./runner-attestation_test.go} internal/app/run/mrjam_attestation_test.go
    substituteInPlace internal/app/run/mrjam_attestation.go \
      --replace-fail '@attestation-client@' '${authorityPackage}/bin/mrjam-validation-request-attestation'
    chmod u+w internal/app/run/mrjam_admission.go
    ${pkgs.python3}/bin/python3 -I -S - <<'PY'
    from pathlib import Path
    path=Path('internal/app/run/mrjam_admission.go')
    value=path.read_text()
    replacements={
      'mrjamExecute(ctx, task, policy, mrjamCollect)': 'mrjamExecute(ctx, task, policy, mrjamCollectAndAttest)',
      'MRJAM_CODE_ARTIFACTS_COLLECTED_NO_DEPLOYMENT_AUTHORITY': 'MRJAM_CODE_ATTESTATION_RETAINED_NO_DEPLOYMENT_AUTHORITY',
      '// No candidate shell, action, checkout, hook or subprocess is executed here.': '// No candidate shell, action, checkout or hook is executed here. Only the fixed authority client runs after collection.',
    }
    for before,after in replacements.items():
      assert value.count(before)==1
      value=value.replace(before,after)
    path.write_text(value)
    PY
  '';
  # Keep the already qualified upstream tests and the bounded admission tests.
  # Added tests cover sequencing/storage; they are not a signature proof.
  passthru = (old.passthru or {}) // { contentAuthorityProtocol = 1; inherit authorityPackage; };
})
