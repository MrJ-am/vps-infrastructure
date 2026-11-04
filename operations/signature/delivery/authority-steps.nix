# Operator-selected checks, never inferred from a candidate's report.
previous:
let
  base = builtins.filter (name: name != "rust-reviewed-readiness-overlay") previous;
  frontends = [ "audition" "log" "logique" "mateval" "style" "style-logo" "vision" ];
  additions = { elm-rules-208 = "signature-resource-regeneration"; }
    // builtins.listToAttrs (map (name: {
      name = "frontend-resource-closure-${name}";
      value = "signature-resource-assembly-${name}";
    }) frontends);
  unique = names: builtins.length (builtins.attrNames
    (builtins.listToAttrs (map (name: { inherit name; value = true; }) names)));
in
assert builtins.length base == 74 && unique base == 74;
assert builtins.all (name: builtins.elem name base) (builtins.attrNames additions);
assert builtins.all (name: builtins.match "signature-.*" name == null) base;
builtins.concatLists (map (name:
  (if builtins.hasAttr name additions then [ additions.${name} ] else []) ++ [ name ]) base)
