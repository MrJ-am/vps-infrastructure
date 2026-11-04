# Render both routes from the deployed host policy, never from candidate Nix.
let
  nixpkgs = /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs = import nixpkgs {};
  baseline = import ../../vise/requalification-20261103/promoted.nix;
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux"; modules = baseline.modules ++ extra;
  }).config;
  blue = evaluate [];
  blueReload = evaluate [{ services.nginx.enableReload = true; }];
  green = evaluate [{ services.nginx.enableReload = true; mrjamVpsApplications.activeSlot = pkgs.lib.mkForce "green"; }];
in assert toString blue.system.build.toplevel == "/nix/store/17lw8y05pgzmcl9q6wvknbf7z1znajl9-nixos-system-srv1982677-26.05pre-git";
assert pkgs.lib.all (a: a.assertion) green.assertions;
pkgs.runCommand "mrjam-deployed-gateway-slot-configurations-001" {
  nativeBuildInputs = [ pkgs.python3 ];
  blueConfig = blueReload.environment.etc."nginx/nginx.conf".source;
  greenConfig = green.environment.etc."nginx/nginx.conf".source;
} ''
  mkdir -p "$out"
  python3 - <<'PY'
  import os,hashlib,json
  from pathlib import Path
  blue=Path(os.environ['blueConfig']);green=Path(os.environ['greenConfig'])
  a=blue.read_bytes();b=green.read_bytes()
  assert a.count(b'127.0.0.1:38101')>0
  assert b==a.replace(b'127.0.0.1:38101',b'127.0.0.1:38102')
  result={'schema_version':1,'code':'ONLY_APPLICATION_UPSTREAM_PORT_DIFFERS',
          'baseline':'17lw8y05pgzmcl9q6wvknbf7z1znajl9','changed_locations':a.count(b'127.0.0.1:38101'),
          'configurations':{slot:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                            for slot,p in [('blue',blue),('green',green)]},
          'production_activation':False}
  (Path(os.environ['out'])/'configurations.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
  PY
''
