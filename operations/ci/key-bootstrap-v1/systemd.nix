{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  locked = import ../../forgejo/locked-toolchain.nix {};
  package = import ./package.nix { pkgs = locked; };
  fixture = pkgs.runCommand "mrjam-key-bootstrap-invented-fixture.py" {} ''
    cp ${./fixture.py} "$out"
    substituteInPlace "$out" --replace-fail '@package@' '${package}' \
      --replace-fail '@openssl@' '${locked.openssl}/bin/openssl' \
      --replace-fail '@runuser@' '${pkgs.util-linux}/bin/runuser' \
      --replace-fail '@python@' '${pkgs.python3}/bin/python3'
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-authority-private-key-bootstrap";
  requiredFeatures.kvm = false;
  qemu.forceAccel = false;
  globalTimeout = 240;
  nodes.machine = {
    system.stateVersion = "26.05";
    networking.hostName = "srv1982677";
    virtualisation.memorySize = 768;
    virtualisation.cores = 2;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    users.groups.invented-outsider.gid = 62000;
    users.users.invented-outsider = { isSystemUser = true; uid = 62000; group = "invented-outsider"; };
    environment.etc."mrjam-key-fixture".text = "INVENTED_VM_ONLY\n";
  };
  testScript = ''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    result=json.loads(machine.succeed("${pkgs.python3}/bin/python3 -I -S ${fixture}",timeout=120))
    assert len(result["checks"])==10
    result["package"]="${package}"
    Path(os.environ["out"],"result.json").write_text(json.dumps(result,sort_keys=True)+"\n")
  '';
}
