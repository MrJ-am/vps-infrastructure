# Immutable, already-qualified code roots. This expression starts no service.
{
  package = builtins.storePath "/nix/store/5yqv8fsy6qhw45qs53qnirib9vl3cjhq-mrjam-kanidm-worker-provision-2";
  unit = builtins.storePath "/nix/store/vzn35cgfpccivnfy42isn0nb125i6xk2-unit-mrjam-kanidm-worker-provision.service";
  portalPackage = builtins.storePath "/nix/store/q7ni6r8bb952mcv08fj919vcdjcvznnq-mrjam-kanidm-passkey-portal-1";
  portalUnit = builtins.storePath "/nix/store/k7gjq9hsvfayhikb9vmwybznr1rp4d8w-unit-mrjam-kanidm-passkey-portal.service";
  resultProbe = builtins.storePath "/nix/store/8inkp30yx0zc86j99bx0pyzazxm45mxn-mrjam-kanidm-worker-result-probe-1";
  routePackage = builtins.storePath "/nix/store/2ibh1gnf1s8c4y77l01ma5jz0fpq8jqd-mrjam-passkey-nginx-route-1";
  routeUnit = builtins.storePath "/nix/store/aingklv82sh1gsxl776808apl0jpzkb5-unit-mrjam-passkey-nginx-route.service";
}
