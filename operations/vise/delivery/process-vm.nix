{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  package=import ../../ci/continuous-delivery-v1/promotion-service.nix {inherit pkgs;};
  server=pkgs.runCommand "mrjam-vise-synthetic-process" {nativeBuildInputs=[pkgs.stdenv.cc];} ''
    mkdir -p "$out"
    cc -Wall -Wextra -Werror -O2 ${./process-vm-server.c} -o "$out/server"
  '';
  command="${pkgs.coreutils}/bin/env PROMOTION_PACKAGE=${package} SYNTHETIC_SERVER=${server}/server ${pkgs.python3}/bin/python3 -I -S ${./process-vm-fixture.py}";
in pkgs.testers.runNixOSTest {
  name="mrjam-vise-real-process-control";globalTimeout=600;
  nodes.machine={lib,...}:{
    system.stateVersion="26.05";
    virtualisation.memorySize=768;virtualisation.cores=1;
    virtualisation.qemu.networkingOptions=lib.mkForce [];virtualisation.vlans=[];
    networking.useDHCP=lib.mkForce false;networking.dhcpcd.enable=false;
    users.groups.vise.gid=981;users.users.vise={isSystemUser=true;uid=981;group="vise";};
    systemd.services.vise={wantedBy=["multi-user.target"];serviceConfig={
      User="vise";Group="vise";ExecStart="${server}/server";Restart="no";
      TimeoutStopSec=5;KillMode="control-group";
    };};
    environment.systemPackages=[pkgs.python3];
  };
  testScript=''
    import json,os
    from pathlib import Path
    machine.start()
    machine.wait_for_unit("vise.service")
    machine.succeed("${command} running")
    machine.fail("${command} stopped")
    machine.succeed("${command} stop")
    machine.succeed("${command} stopped")
    machine.succeed("${command} start")
    machine.succeed("${command} running")
    machine.succeed("systemctl kill --signal=KILL vise.service")
    machine.wait_until_succeeds("test $(systemctl show vise.service -p MainPID --value) = 0")
    machine.fail("${command} stopped")
    machine.succeed("systemctl stop vise.service")
    machine.succeed("PHASE=recovering ${command} stopped")
    machine.succeed("${command} start")
    machine.succeed("${command} running")
    Path(os.environ["out"]).mkdir(exist_ok=True)
    Path(os.environ["out"],"proof.json").write_text(json.dumps({
      "real_systemd":True,"uid":981,"graceful_stop":True,"kill_recovery":True,
      "exact_executable_and_cgroup":True,"health":True,
      "generation_switch_tested":False,"production_access":False}))
  '';
}
