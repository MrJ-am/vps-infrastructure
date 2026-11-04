# Root-owned host state carries these package paths. Candidates cannot set them.
{control}:
{lib,...}:
assert builtins.elem (builtins.attrNames control) [
  ["acceptance" "preparation"] ["acceptance" "preparation" "staging"]
  ["acceptance" "preparation" "stack" "staging"]];
assert lib.all (p: builtins.isString p && builtins.match "/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+" p!=null) (builtins.attrValues control);
{
  imports=[(import ./delivery-preparation-module.nix {packagePath=control.preparation;})]
    ++lib.optional (control ? staging) (import ./staging-service-module.nix {packagePath=control.staging;})
    ++lib.optional (control ? stack) (import ./delivery-stack-module.nix {stackPath=control.stack;inherit control;});
  systemd.services=lib.genAttrs (map (stage: "mrjam-acceptance-${stage}") ["mirror" "review" "merge" "sync"])
    (name: {serviceConfig.ExecStart=lib.mkOverride (-10)
      "${builtins.storePath control.acceptance}/bin/${name}";});
}
