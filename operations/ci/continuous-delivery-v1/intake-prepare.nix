{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {} }:
let
  discovery=import ./github-proposals.nix {inherit pkgs;};
  validator=/nix/store/crhzij9iqk4pya3p9l52n6kraiq3hzg0-mrjam-validate-aligned-workspace-1;
  files=["intake_queue.py" "intake_prepare.py" "intake_bridge.py" "proposal_prepare.py" "source_snapshot.py" "source_fetch.py" "delivery_profiles.py"];
in pkgs.runCommand "mrjam-exact-intake-preparation-1" {nativeBuildInputs=[pkgs.makeWrapper pkgs.python3];} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${discovery}/lib/github_app_auth.py ${discovery}/lib/github_proposals.py "$out/lib/"
  cp ${validator}/lib/policy.py ${validator}/lib/sandbox.py "$out/lib/"
  cp ${../../vise/delivery/source_policy.py} "$out/lib/source_policy.py"
  cp ${../../vise/delivery/source_scope.py} "$out/lib/source_scope.py"
  cp ${/nix/store/26qr08ambmn7g5dccqbr8q7aqkvcd92f-check_git_tree.py} "$out/lib/check_git_tree.py"
  ${pkgs.lib.concatMapStringsSep "\n" (name: "cp ${./. + ("/" + name)} \"$out/lib/${name}\"") files}
  cp ${./intake-prepare-entry.py} "$out/lib/entry.py"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-intake-prepare" \
    --add-flags '-I -S' --add-flags "$out/lib/entry.py" \
    --set MRJAM_INTAKE_GIT ${pkgs.gitMinimal}/bin/git
  python3 -I -S - "$out/lib" <<'PY'
  import sys
  sys.path.insert(0,sys.argv[1])
  import entry,intake_prepare,policy
  PY
''
