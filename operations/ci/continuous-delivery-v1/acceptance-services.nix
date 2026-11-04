{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}
, admissionController ? /nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1
, anchorControl ? /nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1
, enableVise ? false}:
let
  recipe=import ./delivery-recipe.nix {inherit pkgs;};
  installed = value: if builtins.isAttrs value then value else builtins.storePath value;
  files=["acceptance_service.py" "acceptance_pipeline.py" "acceptance_adapter.py" "acceptance_commit.py" "staging_gate.py"
    "staging_runtime.py" "delivery_environment.py" "generation_views.py" "delivery_stack.py"
    "forge_proposal.py" "forge_review.py" "forge_merge.py" "github_accepted_main.py" "delivery_roles.py" "delivery_profiles.py"];
in pkgs.runCommand "mrjam-separated-acceptance-services-1" {
  admission=installed admissionController;
  anchor=installed anchorControl;
  nativeBuildInputs=[pkgs.makeWrapper pkgs.python3];
} ''
  mkdir -p "$out/lib" "$out/bin"
  ${pkgs.lib.concatMapStringsSep "\n" (name: "cp ${./. + ("/"+name)} \"$out/lib/${name}\"") files}
  substituteInPlace "$out/lib/acceptance_service.py" \
    --replace-fail "ADMISSION='/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1'" "ADMISSION='$admission'" \
    --replace-fail "ANCHOR='/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1'" "ANCHOR='$anchor'" \
    --replace-fail 'ENABLE_VISE=False' 'ENABLE_VISE=${if enableVise then "True" else "False"}' \
    --replace-fail '@delivery-recipe@' '${recipe}'
  for stage in mirror review merge sync; do
    makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-acceptance-$stage" \
      --add-flags '-I -S' --add-flags "$out/lib/acceptance_service.py" \
      --set MRJAM_ACCEPTANCE_STAGE "$stage" --set MRJAM_ACCEPTANCE_GIT ${pkgs.git}/bin/git
  done
  python3 -I -S - "$out/lib" <<'PY'
  import sys
  sys.path.insert(0,sys.argv[1])
  import acceptance_service as service
  from pathlib import Path
  sys.path.extend([str(Path(service.RECIPE)/'operations/vise/delivery'),
      str(Path(service.RECIPE)/'operations/ci/continuous-delivery-v1')])
  import acceptance_gate,preparation_plan
  assert callable(acceptance_gate.ready) and callable(preparation_plan.create)
  if service.ENABLE_VISE:
      from pathlib import Path
      import admission_registry as R,admission_control as A
      original=R.store_bytes
      try:
          R.store_bytes=lambda path,maximum=131072:Path(path).read_bytes()
          A.anchor_for('vise-v1')
      finally:R.store_bytes=original
  PY
''
