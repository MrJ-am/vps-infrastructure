let
  lib=(import ../../forgejo/locked-toolchain.nix {}).lib;
  factory=args: import ./admission-package.nix args;
  rejects=validity: !(builtins.tryEval (toString (factory {inherit validity;}))).success;
  checks=(import ./proposal-bindings-qualification.nix).evaluation // {
    defaultControlUnchanged=toString (factory {})=="/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1";
    missingExpiryRefused=rejects {not_before=1;};
    unknownFieldRefused=rejects {not_before=1;expires_at=2;skip=true;};
    nonIntegerRefused=rejects {not_before="1";expires_at=2;};
    zeroStartRefused=rejects {not_before=0;expires_at=2;};
    reversedRefused=rejects {not_before=2;expires_at=1;};
    unboundedRefused=rejects {not_before=1;expires_at=604802;};
    boundedWindowAccepted=(factory {validity={not_before=1;expires_at=604801;};}).policy.expires_at==604801;
  };
in assert lib.all (x: x) (builtins.attrValues checks);checks
