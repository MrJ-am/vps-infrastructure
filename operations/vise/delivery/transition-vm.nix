{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}, crashPoint ? "", recoveryCase ? false, rebootBeforeResume ? false, queueCase ? false}:
let
  package=import ../../ci/continuous-delivery-v1/promotion-service.nix {inherit pkgs;};
  makeServer=version: pkgs.runCommand "mrjam-vise-synthetic-${version}" {nativeBuildInputs=[pkgs.stdenv.cc];} ''
    mkdir -p "$out/dist"
    cc -Wall -Wextra -Werror -O2 ${./process-vm-server.c} -o "$out/server"
    echo synthetic > "$out/dist/index.html"
  '';
  old=makeServer "old";new=makeServer "new";
  platformAdopted=pkgs.writeText "mrjam-synthetic-platform-adoption.json" "{}";
  adopted=pkgs.writeText "mrjam-synthetic-vise-adoption.json" "{}";
  descriptor=pkgs.writeText "mrjam-synthetic-vise-candidate.json" (builtins.toJSON {
    schema_version=2;profile="vise-v1";deployment_authorized=false;bundle=new;inherit adopted;
  });
  candidate=pkgs.runCommand "mrjam-synthetic-vise-candidate" {} ''
    mkdir "$out";ln -s ${descriptor} "$out/descriptor.json"
  '';
  settings=pkgs.writeText "mrjam-vise-transition-vm.json" (builtins.toJSON {
    inherit package old new platformAdopted adopted candidate crashPoint recoveryCase queueCase;
  });
in pkgs.testers.runNixOSTest {
  name="mrjam-vise-real-generation-transition";globalTimeout=900;
  nodes.machine={lib,...}:{
    system.stateVersion="26.05";
    virtualisation.memorySize=1024;virtualisation.cores=1;
    virtualisation.useBootLoader=true;
    virtualisation.qemu.networkingOptions=lib.mkForce [];virtualisation.vlans=[];
    networking.useDHCP=lib.mkForce false;networking.dhcpcd.enable=false;
    # The specialisation helper changes system-path; this fixture has no D-Bus
    # applications and keeps that unrelated configuration fixed in both views.
    services.dbus.packages=lib.mkForce [pkgs.dbus pkgs.systemd];
    users.groups.vise.gid=981;users.users.vise={isSystemUser=true;uid=981;group="vise";};
    environment.etc."nginx/nginx.conf".text="# synthetic retained route\n";
    environment.etc."mrjam-delivery-adopted.json".source=platformAdopted;
    environment.systemPackages=[pkgs.nix];
    systemd.services=lib.genAttrs ["nginx" "postgresql" "forgejo" "mrjam-rust-blue" "mrjam-rust-green" "mrjam-forgejo-runner"]
      (_:{wantedBy=["multi-user.target"];serviceConfig.ExecStart="${pkgs.coreutils}/bin/sleep infinity";}) // {
      vise={wantedBy=["multi-user.target"];restartIfChanged=false;stopIfChanged=false;
        environment.DIST_DIR="${old}/dist";
        serviceConfig={User="vise";Group="vise";ExecStart="${old}/server";Restart="no";TimeoutStopSec=5;KillMode="control-group";};};
      vise-transition-test={
        environment.VM_CONFIG=toString settings;
        serviceConfig={Type="oneshot";RemainAfterExit=true;TimeoutStartSec=300;
          ExecStart="${pkgs.python3}/bin/python3 -I -S ${./transition-vm-fixture.py}";};
      };
    };
    specialisation.candidate.configuration={lib,...}:{
      systemd.services.vise.serviceConfig.ExecStart=lib.mkForce "${new}/server";
      systemd.services.vise.environment.DIST_DIR=lib.mkForce "${new}/dist";
      environment.etc."mrjam-vise-delivery-adopted.json".source=adopted;
    };
  };
  testScript=''
    import json,os
    from pathlib import Path
    machine.start(allow_reboot=True);machine.wait_for_unit("vise.service")
    crash_point=${builtins.toJSON crashPoint}
    recovery_case=${if recoveryCase then "True" else "False"}
    if crash_point:
      machine.fail("systemctl start vise-transition-test",timeout=360)
      interrupted=json.loads(machine.succeed("cat /var/lib/mrjam-promotion/interrupted.json"))
      assert interrupted=={"point":crash_point,"signal":"SIGKILL"}
      assert machine.succeed("systemctl show vise-transition-test -p ExecMainCode --value").strip()=="2"
      assert machine.succeed("systemctl show vise-transition-test -p ExecMainStatus --value").strip()=="9"
      machine.succeed("systemctl reset-failed vise-transition-test")
      if ${if rebootBeforeResume then "True" else "False"}:
        machine.reboot()
        machine.wait_for_unit("multi-user.target")
        machine.wait_for_unit("vise.service")
    machine.succeed("systemctl start vise-transition-test",timeout=360)
    proof=json.loads(machine.succeed("cat /var/lib/mrjam-promotion/proof.json"))
    plan=json.loads(machine.succeed("cat /var/lib/mrjam-promotion/plan.json"))
    events=json.loads(machine.succeed("cat /var/lib/mrjam-promotion/events.json"))
    phases={row["phase"]:row for row in events}
    target="old" if recovery_case else "new"
    expected="VISE_FAILED" if recovery_case else "VISE_COMPLETE"
    if recovery_case:
      assert "recovering" in phases and "complete" not in phases
      assert phases["failed"]["current"]==phases["failed"]["boot"]==plan["old"]
    else:
      assert phases["new-tested"]["current"]==plan["new"]
      assert phases["returned"]["current"]==plan["old"]
      assert phases["complete"]["current"]==phases["complete"]["boot"]==plan["new"]
    machine.succeed("systemctl is-active vise nginx postgresql forgejo mrjam-rust-blue mrjam-rust-green mrjam-forgejo-runner")
    machine.reboot()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("vise.service")
    assert machine.succeed("readlink -f /run/current-system").strip()==plan[target]
    assert machine.succeed("readlink -f /nix/var/nix/profiles/system").strip()==plan[target]
    machine.succeed("systemctl start vise-transition-test",timeout=60)
    resumed=json.loads(machine.succeed("cat /var/lib/mrjam-promotion/proof.json"))
    assert resumed["result"]["code"]==expected
    assert resumed["result"].get("previous_restored" if recovery_case else "recovered")
    Path(os.environ["out"]).mkdir(exist_ok=True)
    Path(os.environ["out"],"proof.json").write_text(json.dumps({**proof,"events":events,
      "real_reboot":True,"completed_receipt_resumed_after_reboot":not recovery_case,
      "recovery_case":recovery_case,"reboot_before_resume":${if rebootBeforeResume then "True" else "False"},
      "controller_sigkill_point":crash_point,"controller_resumed_after_sigkill":bool(crash_point)}))
  '';
}
