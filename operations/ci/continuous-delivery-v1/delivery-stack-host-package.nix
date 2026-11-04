# Export one already reviewed composition for evaluation/build, never activation.
{stateFile, stackPath, recipePath, baselineRecipePath, expectedSystem,
 pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  store=p: builtins.isString p && builtins.match "/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+" p!=null;
  stack=builtins.storePath stackPath;
  recipe=builtins.storePath recipePath;
  baselineRecipe=builtins.storePath baselineRecipePath;
  state=builtins.path {path=stateFile;name="mrjam-stack-observed-state.json";};
  entry=pkgs.writeText "mrjam-stack-build-entry.nix" ''
    let host=import ./host.nix {
      stateFile="${state}";
      stackPath="${stack}";
      baselineRecipePath="${baselineRecipe}";
    };
    in assert host.evaluation.state.system=="${expectedSystem}";host
  '';
  manifest=pkgs.writeText "mrjam-stack-build-binding.json" (builtins.toJSON {
    schema_version=1;deployment_authorized=false;inherit expectedSystem;
    stack=stack;recipe=recipe;state=state;baselineRecipe=baselineRecipe;
    state_sha256=builtins.hashFile "sha256" state;
    composition_sha256=builtins.hashFile "sha256" ./delivery-stack-host.nix;
  });
in assert pkgs.lib.all store [stackPath recipePath baselineRecipePath expectedSystem];
pkgs.runCommand "mrjam-protected-stack-host-build-1" {} ''
  mkdir "$out"
  cp ${./delivery-stack-host.nix} "$out/host.nix"
  substituteInPlace "$out/host.nix" --replace-fail \
    'modules ./delivery-control-plane.nix' \
    'modules ${recipe}/operations/ci/continuous-delivery-v1/delivery-control-plane.nix'
  cp ${entry} "$out/default.nix"
  cp ${manifest} "$out/binding.json"
  # Exit the evaluator before compilation so its heap cannot crowd out Go.
  mkdir "$out/bin"
  cat > "$out/bin/build" <<EOF
  #!${pkgs.runtimeShell}
  set -eu
  test "\$#" -eq 0 || exit 64
  drv=\$(${pkgs.nix}/bin/nix-instantiate "$out" -A toplevel)
  case "\$drv" in /nix/store/*.drv) ;; *) exit 65 ;; esac
  exec ${pkgs.nix}/bin/nix-store --realise "\$drv" --option builders "" --max-jobs 1 --cores 1
  EOF
  chmod 0555 "$out/bin/build"
''
