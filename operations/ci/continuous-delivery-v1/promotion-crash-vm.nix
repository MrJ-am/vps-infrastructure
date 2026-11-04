{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
pkgs.testers.runNixOSTest {
  name="mrjam-promotion-durable-recovery";
  globalTimeout=600;
  nodes.machine={lib,...}:{
    system.stateVersion="26.05";
    virtualisation.memorySize=768;virtualisation.cores=1;
    virtualisation.qemu.networkingOptions=lib.mkForce [];virtualisation.vlans=[];
    networking.useDHCP=lib.mkForce false;networking.dhcpcd.enable=false;
    environment.etc."promotion-synthetic/promotion_transaction.py".source=./promotion_transaction.py;
    environment.etc."promotion-synthetic/source_snapshot.py".source=./source_snapshot.py;
    environment.etc."promotion-synthetic/fixture.py".source=./promotion-crash-fixture.py;
    systemd.services."promotion-synthetic@"={
      environment.CASE_INDEX="%i";
      serviceConfig={
        Type="oneshot";RemainAfterExit=true;Restart="on-failure";RestartSec="100ms";
        ExecStart="${pkgs.python3}/bin/python3 -I -S /etc/promotion-synthetic/fixture.py";
        StateDirectory="promotion-case-%i";StateDirectoryMode="0700";
        ProtectSystem="strict";ProtectHome=true;PrivateNetwork=true;PrivateDevices=true;
        NoNewPrivileges=true;CapabilityBoundingSet="";UMask="0077";
      };
    };
  };
  testScript=''
    import json,os
    from pathlib import Path
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.succeed("systemctl start promotion-synthetic@0")
    base=json.loads(machine.succeed("cat /var/lib/promotion-case-0/proof.json"))
    assert base["complete"] and not base["crashed"]
    count=base["events"]
    assert 20<=count<=100
    for cut in range(1,count+1):
        machine.succeed(f"systemctl start --no-block promotion-synthetic@{cut}")
        machine.wait_until_succeeds(f"test -f /var/lib/promotion-case-{cut}/proof.json",timeout=30)
        proof=json.loads(machine.succeed(f"cat /var/lib/promotion-case-{cut}/proof.json"))
        assert proof["complete"] and proof["crashed"] and proof["separate_durable_files"]
        job=json.loads(machine.succeed(f"cat /var/lib/promotion-case-{cut}/job.json"))
        assert job=={"deployed":True,"marker":False}
    Path(os.environ["out"]).mkdir(exist_ok=True)
    Path(os.environ["out"],"promotion-crash-proof.json").write_text(json.dumps({
      "real_process_termination_cases":count,"systemd_restart_verified":True,
      "separate_durable_files":True,"synthetic_only":True,"production_activation":False}))
  '';
}
