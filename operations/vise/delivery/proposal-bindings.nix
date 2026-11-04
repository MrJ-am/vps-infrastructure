# Protected constructor inputs only; never import Nix supplied by a proposal.
{ preparedSource, policyFile, proposal
, rulesSource ? null, rulesRevision ? null
, pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}
, dependencies ? builtins.storePath /nix/store/0ddv9m7ylgn7ri86p9n0z0yy1gn2nxh7-mrjam-vise-validation-dependencies-1
}:
let
  # The existing generic manifest copier is lazy: its platform validator is
  # not evaluated or built when only this source output is selected.
  source=(import ../../ci/continuous-delivery-v1/proposal-bindings.nix {
    inherit pkgs preparedSource policyFile proposal;
  }).source;
  report=builtins.fromJSON (builtins.readFile policyFile);
  validator=if rulesSource!=null then import ./canonical-validator.nix {
    inherit pkgs policyFile dependencies rulesSource rulesRevision;
  } else assert report.rules_revision=="0000000000000000000000000000000000000000";
    import ./build-probe.nix {inherit pkgs policyFile dependencies;probe="validation";};
  closure=pkgs.closureInfo {rootPaths=[validator];};
in {inherit source validator closure proposal;}
