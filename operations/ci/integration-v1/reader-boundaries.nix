{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  authority = /nix/store/d48pqnf7q0hfqkhvbg6vd0nk6ffihzy5-mrjam-validation-authority-credentials-2;
  fixture = pkgs.runCommand "mrjam-invented-credential-reader-boundaries.py" {} ''
    cp ${./reader-boundaries.py} "$out"
    substituteInPlace "$out" \
      --replace-fail '@authority@' '${authority}' \
      --replace-fail '@mount@' '${pkgs.util-linux}/bin/mount' \
      --replace-fail '@unshare@' '${pkgs.util-linux}/bin/unshare' \
      --replace-fail '@python@' '${pkgs.python3}/bin/python3'
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-authority-exact-reader-kernel-boundaries";
  requiredFeatures.kvm = false;
  qemu.forceAccel = false;
  globalTimeout = 240;
  nodes.machine = {
    system.stateVersion = "26.05";
    virtualisation.memorySize = 768;
    virtualisation.cores = 2;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    users.groups.invented-signer.gid = 61002;
    users.users.invented-signer = { isSystemUser = true; uid = 61002; group = "invented-signer"; };
    environment.etc."mrjam-reader-fixture".text = "INVENTED_VM_ONLY\n";
  };
  testScript = ''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    result=json.loads(machine.succeed("${pkgs.python3}/bin/python3 -I -S ${fixture}",timeout=120))
    assert len(result["checks"])==9
    assert [x["accepted"] for x in result["checks"]]==[True,False,False,False,False,False,False,False,True]
    Path(os.environ["out"],"result.json").write_text(json.dumps(result,sort_keys=True)+"\n")
  '';
}
