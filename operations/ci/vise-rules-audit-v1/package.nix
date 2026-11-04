# The proposal supplies rule bytes only; the operator selects expectations.
{rulesSource,
 pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  source=builtins.path {path=rulesSource;name="mrjam-vise-rules-proposal-470211d";};
  binding=../vise-rules-proposal-v1/binding.json;
  gate=builtins.storePath "/nix/store/26qr08ambmn7g5dccqbr8q7aqkvcd92f-check_git_tree.py";
  shared=["source_snapshot.py" "proposal_prepare.py" "proposal_policy.py"];
in assert builtins.hashFile "sha256" binding=="f1be13306d02a8e598efdd5c127910c6464392d7f234441bd07d9b441f05ecdc";
pkgs.runCommand "mrjam-vise-rules-independent-audit-1" {
  nativeBuildInputs=[pkgs.python3 pkgs.gitMinimal];
  preferLocalBuild=true;
} ''
  mkdir -p "$out" harness/shared
  test -f ${gate}
  ${pkgs.lib.concatMapStringsSep "\n" (name:
    "cp ${../continuous-delivery-v1 + ("/"+name)} harness/shared/${name}") shared}
  cp ${./contract_tests.py} harness/contract_tests.py
  cp ${../../vise/delivery/test_source_policy.py} harness/source_policy_tests.py
  ${pkgs.python3}/bin/python3 -I -S -B ${./run.py} \
    ${source} ${binding} "$PWD/harness/contract_tests.py" \
    "$PWD/harness/source_policy_tests.py" "$PWD/harness/shared" "$out/report.json"
  test -s "$out/report.json"
  cp ${binding} "$out/binding.json"
  ln -s ${source} "$out/proposal"
''
