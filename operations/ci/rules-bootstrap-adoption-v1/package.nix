{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source { system = "x86_64-linux"; }
, proposalPackage ? builtins.storePath /nix/store/1j61zvqin8df0vdazsdxlfssf5rdc54z-mrjam-rules-bootstrap-proposal-1 }:
pkgs.runCommand "mrjam-rules-bootstrap-adoption-1" {} ''
  mkdir -p "$out/libexec" "$out/bin"
  cp ${./adoption.py} "$out/libexec/adoption.py"
  cp ${./identity.py} "$out/libexec/identity.py"
  cp ${./merge_transport.py} "$out/libexec/merge_transport.py"
  cp ${../../deployment/forgejo_sso_probe.py} "$out/libexec/sso.py"
  cp ${../authority-v1/contract.py} "$out/libexec/contract.py"
  cp ${../authority-v1/signer.py} "$out/libexec/signer.py"
  cp ${../authority-v1/collector.py} "$out/libexec/collector.py"
  cp ${../review-v1/review_contract.py} "$out/libexec/review_contract.py"
  cp ${../review-v1/api_projection.py} "$out/libexec/api_projection.py"
  cp ${../review-v1/read_transport_v2.py} "$out/libexec/read_transport_v2.py"
  substitute ${./entry.py} "$out/libexec/bootstrap-entry.py" --subst-var-by PROPOSAL ${proposalPackage}
  cat > "$out/bin/mrjam-adopt-initial-rules" <<EOF
#!${pkgs.runtimeShell}
exec ${pkgs.python3}/bin/python3 -I -S -B "$out/libexec/bootstrap-entry.py" "\$@"
EOF
  chmod 0555 "$out/bin/mrjam-adopt-initial-rules"
''
