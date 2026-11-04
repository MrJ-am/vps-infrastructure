{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  proposal=pkgs.callPackage ../vise-rules-proposal-v1/package.nix {
    bindingFile=../vise-rules-proposal-v1/binding.json;
    bindingSha256="f1be13306d02a8e598efdd5c127910c6464392d7f234441bd07d9b441f05ecdc";
  };
  audit=builtins.storePath "/nix/store/74329d2w5p244s4rvpfip1c70cvb4qid-mrjam-vise-rules-independent-audit-1";
in assert builtins.hashFile "sha256" (audit+"/report.json")=="01c207fc0880e270a597c0d3a4657bd1b3e95df3355aab267d96b3d4f484bdba";
pkgs.runCommand "mrjam-vise-rules-audit-publisher-1" {} ''
  mkdir -p "$out/libexec" "$out/bin"
  for name in core lease protection reconcile credentials; do
    ln -s ${proposal}/libexec/$name.py "$out/libexec/$name.py"
  done
  ln -s ${proposal}/libexec/entry.py "$out/libexec/proposal_entry.py"
  cp ${./publish.py} "$out/libexec/publish.py"
  substitute ${./publish-entry.py} "$out/libexec/entry.py" --subst-var-by AUDIT ${audit}
  ln -s ${audit} "$out/audit"
  cat > "$out/bin/publish" <<EOF
#!${pkgs.runtimeShell}
exec ${pkgs.python3}/bin/python3 -I -S -B "$out/libexec/entry.py" "\$@"
EOF
  chmod 0555 "$out/bin/publish"
''
