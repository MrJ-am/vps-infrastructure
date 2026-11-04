{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {},
 acceptanceServices ? /nix/store/zf97rkdq655qhfa9zijwyzvjinambdkv-mrjam-separated-acceptance-services-1,
 admissionController ? /nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1,
 anchorControl ? /nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1}:
let installed=value: if builtins.isAttrs value then value else builtins.storePath value;
 files=["staging_service.py" "staging_queue.py" "staging_plan.py" "staging_lease.py"
  "staging_adapter.py" "staging_transaction.py" "staging_runtime.py" "staging_layout.py" "delivery_constructor.py"
  "delivery_environment.py" "generation_views.py" "delivery_stack.py" "promotion_enqueue.py" "promotion_reservation.py"
  "verified_delivery.py" "delivery_frontends.py" "accepted_receipts.py" "delivery_profiles.py" "acceptance_commit.py"];
in pkgs.runCommand "mrjam-protected-staging-service-1" {
  observer=installed acceptanceServices;
  admission=installed admissionController;
  anchor=installed anchorControl;
  nativeBuildInputs=[pkgs.makeWrapper];
} ''
  mkdir -p "$out/lib" "$out/bin"
  ${pkgs.lib.concatMapStringsSep "\n" (name: "cp ${./. + ("/"+name)} \"$out/lib/${name}\"") files}
  substituteInPlace "$out/lib/staging_service.py" \
    --replace-fail '/nix/store/zf97rkdq655qhfa9zijwyzvjinambdkv-mrjam-separated-acceptance-services-1/lib' "$observer/lib" \
    --replace-fail '/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1/lib' "$admission/lib" \
    --replace-fail '/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib' "$anchor/lib"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-delivery-stage" \
    --add-flags '-I -S' --add-flags "$out/lib/staging_service.py"
  ${pkgs.python3}/bin/python3 -I -S - "$out/lib" <<'PY'
  import sys
  sys.path.insert(0,sys.argv[1])
  import staging_service
  assert callable(staging_service.L.K.returned)
  PY
''
