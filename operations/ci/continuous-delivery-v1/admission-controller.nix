{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}
, anchorControl ? builtins.storePath "/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1"
, enableVise ? false}:
let
  installedAnchor=if builtins.isAttrs anchorControl then anchorControl else builtins.storePath anchorControl;
  intake=import ./intake-prepare.nix {inherit pkgs;};
  recipe=import ./captured-admission-recipe.nix {inherit pkgs;};
  toolchainSource=builtins.storePath "/nix/store/ydk30pf7qngrw0ws113m9p005p681rxy-source";
  files=["intake_capture.py" "proposal_policy.py" "source_observation.py" "delivery_capture.py"
    "validation_dispatch.py" "validation_feedback.py" "admission_orchestrator.py" "admission_adapter.py" "admission_profiles.py"];
in pkgs.runCommand "mrjam-protected-admission-controller-1" {anchorControl=installedAnchor;nativeBuildInputs=[pkgs.makeWrapper pkgs.python3];} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${intake}/lib/*.py "$out/lib/"
  ${pkgs.lib.concatMapStringsSep "\n" (name: "cp ${./. + ("/"+name)} \"$out/lib/${name}\"") files}
  cp ${../../forgejo/stage_sources.py} "$out/lib/stage_sources.py"
  cp ${../../forgejo/worker.py} "$out/lib/worker.py"
  cp ${./admission-controller-entry.py} "$out/lib/controller.py"
  substituteInPlace "$out/lib/controller.py" \
    --replace-fail "ANCHOR_CONTROL='/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1'" "ANCHOR_CONTROL='${installedAnchor}'" \
    --replace-fail 'ENABLE_VISE=False' 'ENABLE_VISE=${if enableVise then "True" else "False"}'
  echo ${toolchainSource} > "$out/lib/toolchain-source"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-admission-controller" \
    --add-flags '-I -S' --add-flags "$out/lib/controller.py" \
    --set MRJAM_ADMISSION_RECIPE ${recipe} --set MRJAM_NIX_BUILD ${pkgs.nix}/bin/nix-build
  python3 -I -S - "$out/lib" <<'PY'
  import sys
  sys.path.insert(0,sys.argv[1])
  import controller,admission_adapter,admission_orchestrator
  assert controller.ANCHOR_CONTROL=='${installedAnchor}'
  if controller.ENABLE_VISE:
      # Build namespaces remap root; validate immutable policy content here.
      # Installed runtime store_bytes keeps its strict owner/mode checks.
      from pathlib import Path
      original=controller.R.store_bytes
      try:
          controller.R.store_bytes=lambda path,maximum=131072:Path(path).read_bytes()
          controller.A.anchor_for('vise-v1')
      finally:controller.R.store_bytes=original
  PY
''
