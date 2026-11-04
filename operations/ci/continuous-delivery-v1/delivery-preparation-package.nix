{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {},
 admissionControl ? /nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1,
 admissionController ? /nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1,
 enableVise ? false}:
let recipe=import ./delivery-recipe.nix {inherit pkgs;};
    installed=value: if builtins.isAttrs value then value else builtins.storePath (toString value);
    control=installed admissionControl;
    controller=installed admissionController;
    service=pkgs.writeText "delivery-preparation-service.py" (builtins.replaceStrings
      ["@enable-vise@"
       "/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1"
       "/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1"]
      [(if enableVise then "true" else "false") (toString control) (toString controller)]
      (builtins.readFile ./delivery_preparation_service.py));
in assert builtins.isBool enableVise;
pkgs.runCommand "mrjam-delivery-preparation-1" {nativeBuildInputs=[pkgs.makeWrapper];} ''
  mkdir -p "$out/bin" "$out/lib"
  test -f ${control}/lib/admission_control.py
  test -f ${controller}/lib/admission_orchestrator.py
  cp ${service} "$out/lib/service.py"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-delivery-prepare" \
    --add-flags '-I -S' --add-flags "$out/lib/service.py" \
    --set MRJAM_DELIVERY_RECIPE ${recipe} --set MRJAM_DELIVERY_NIX ${pkgs.nix}
''
