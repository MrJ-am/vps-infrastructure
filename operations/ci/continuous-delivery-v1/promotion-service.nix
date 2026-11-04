{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {},
 admissionController ? /nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1,
 anchorControl ? /nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1,
 enableVise ? false}:
let recipe=import ./promotion-runtime.nix {inherit pkgs;};
    installed=value: if builtins.isAttrs value then value else builtins.storePath value;
    files=["promotion_service.py" "promotion_transaction.py" "promotion_reservation.py" "verified_delivery.py"
  "forge_proposal.py" "forge_review.py" "forge_merge.py" "delivery_roles.py" "delivery_frontends.py"];
in pkgs.runCommand "mrjam-protected-promotion-service-1" {
  anchor=installed anchorControl;
  admission=installed admissionController;
  nativeBuildInputs=[pkgs.makeWrapper];
} ''
  mkdir -p "$out/lib" "$out/bin"
  ${pkgs.lib.concatMapStringsSep "\n" (name: "cp ${./. + ("/"+name)} \"$out/lib/${name}\"") files}
  substituteInPlace "$out/lib/promotion_service.py" \
    --replace-fail "ADMISSION='/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1'" "ADMISSION='$admission'" \
    --replace-fail "ANCHOR='/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1'" "ANCHOR='$anchor'" \
    --replace-fail 'ENABLE_VISE=False' 'ENABLE_VISE=${if enableVise then "True" else "False"}' \
    --replace-fail '@delivery-recipe@' '${recipe}'
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-promotion" --add-flags '-I -S' --add-flags "$out/lib/promotion_service.py"
  ${pkgs.python3}/bin/python3 -I -S - "$out/lib" <<'PY'
  import sys
  from pathlib import Path
  sys.path.insert(0,sys.argv[1])
  import promotion_service as service
  sys.path.extend([str(Path(service.RECIPE)/'operations/vise/delivery'),
      str(Path(service.RECIPE)/'operations/ci/continuous-delivery-v1')])
  import transition_adapter,transition,enqueue,queue_tick
  assert callable(queue_tick.tick)
  assert callable(transition_adapter.Adapter) and callable(transition.promote) and callable(enqueue.publish)
  if service.ENABLE_VISE:
      import admission_registry as R
      original=R.store_bytes
      try:
          R.store_bytes=lambda path,maximum=131072:Path(path).read_bytes()
          service.A.anchor_for('vise-v1')
      finally:R.store_bytes=original
  PY
''
