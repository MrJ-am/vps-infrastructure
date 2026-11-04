# Reconstruct the already accepted source through the generic protected recipe.
let
  pkgs=import ../../forgejo/locked-toolchain.nix {};
  bindings=import ./proposal-bindings.nix {
    inherit pkgs;
    preparedSource=../../../.local/deployment-20261101/aligned-proposal-003;
    policyFile=./aligned-policy.json;
    proposal="04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d";
  };
  control=import ./admission-package.nix {inherit pkgs bindings;};
in {
  source=bindings.source;
  evaluation={
    sameValidator=toString bindings.validator=="/nix/store/crhzij9iqk4pya3p9l52n6kraiq3hzg0-mrjam-validate-aligned-workspace-1";
    sameControl=toString control=="/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1";
    sameProposal=bindings.proposal=="04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d";
  };
}
