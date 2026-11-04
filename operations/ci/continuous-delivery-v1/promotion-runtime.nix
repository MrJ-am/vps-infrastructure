{pkgs}:
let
  shared=["accepted_receipts.py" "acceptance_commit.py" "acceptance_pipeline.py"
    "delivery_profiles.py" "generation_views.py" "promotion_enqueue.py"
    "staging_lease.py" "staging_transaction.py" "delivery_environment.py" "delivery_stack.py"
    "staging_runtime.py" "staging_layout.py"];
  vise=["accepted_plan.py" "enqueue.py" "queue_tick.py" "generation_layout.py" "package_content.py"
    "process_state.py" "transition.py" "transition_adapter.py" "vise_verified_delivery.py"];
in pkgs.runCommand "mrjam-protected-promotion-runtime-1" {} ''
  mkdir -p "$out/operations/ci/continuous-delivery-v1" "$out/operations/vise/delivery"
  ${pkgs.lib.concatMapStringsSep "\n" (name: "cp ${./. + ("/"+name)} \"$out/operations/ci/continuous-delivery-v1/${name}\"") shared}
  ${pkgs.lib.concatMapStringsSep "\n" (name: "cp ${../../vise/delivery + ("/"+name)} \"$out/operations/vise/delivery/${name}\"") vise}
''
