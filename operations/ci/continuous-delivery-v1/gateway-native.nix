{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {} }:
pkgs.runCommand "mrjam-graceful-gateway-native-001" {
  nativeBuildInputs = [ pkgs.python3 ];
} ''
  mkdir -p "$out" work
  cp ${./gateway_switch.py} work/gateway_switch.py
  cp ${./test_gateway_native.py} work/test_gateway_native.py
  python3 work/test_gateway_native.py ${pkgs.nginx}/bin/nginx "$out/result.json"
''
