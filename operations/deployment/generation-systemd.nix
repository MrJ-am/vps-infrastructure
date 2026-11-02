{ nixpkgs }:
let
  pkgs=import nixpkgs { system="x86_64-linux"; };
  guard=import ./boot-guard-package.nix { inherit pkgs; };
  operation=pkgs.writeText "synthetic-generation-operation.py" ''
    import json,os,sys,subprocess
    from pathlib import Path
    sys.path.insert(0,"/etc/cutover-fixture")
    from generation import Generations
    from cutover import Checkpoint,Phase
    from system_control import SystemControl,ALLOWED
    root=Path("/var/lib/mrjam-cutover/first-deployment")
    roots=json.loads(Path("/run/synthetic-generations.json").read_text())
    gen=Generations(roots["previous"],roots["staged"],roots["promoted"],"${pkgs.nix}/bin/nix-env")
    phase=Checkpoint(root)
    control=SystemControl("${pkgs.systemd}/bin/systemctl","${pkgs.nftables}/bin/nft","${guard}/bin/mrjam-first-cutover-guard")
    action=sys.argv[1]
    if action=="stage-boot":
        gen.verify_previous()
        phase.write(Phase.FREEZING,0)
        gen.select_boot(gen.staged)
        assert os.path.realpath("/run/current-system")==gen.previous
    elif action=="private":
        phase.write(Phase.SNAPSHOT,10)
        gen.activate(gen.staged)
        phase.write(Phase.CANDIDATE,11)
    elif action in ("return-private","return"):
        phase.write(Phase.RETURNING,20)
        # The real previous generation has no cutover generator. The portable
        # early generator must survive its activation and override /etc units.
        control.masked_here=set(ALLOWED)
        control.publish_masks()
        control.execute([control.systemctl,"daemon-reload"],timeout=60)
        control.verify_masks()
        gen.activate(gen.previous)
        control.verify_masks()
        assert os.path.realpath('/nix/var/nix/profiles/system')==gen.staged
        if action=="return":
            phase.write(Phase.RETURNED,25)
            gen.select_boot(gen.previous)
            control.release_masks(tuple(ALLOWED))
    elif action=="promote":
        phase.write(Phase.OPENING,30)
        gen.select_boot(gen.promoted)
        gen.activate(gen.promoted)
        phase.write(Phase.OPEN,35)
    else:
        raise RuntimeError("SYNTHETIC_ACTION_REFUSED")
  '';
in pkgs.testers.runNixOSTest {
  name="mrjam-exact-generation-switch-and-boot";
  requiredFeatures.kvm=true;
  globalTimeout=900;
  nodes.machine={lib,...}: {
    system.stateVersion="26.05";
    virtualisation.memorySize=1024;
    virtualisation.cores=1;
    virtualisation.vlans=[];
    virtualisation.useBootLoader=true;
    boot.loader.grub.enable=true;
    boot.loader.grub.device="/dev/vda";
    boot.loader.timeout=1;
    networking.hostName="generation-synthetic";
    environment.systemPackages=[ pkgs.nix pkgs.python3 ];
    system.extraDependencies=[ operation ];
    environment.etc."cutover-fixture/generation.py".source=./generation.py;
    environment.etc."cutover-fixture/cutover.py".source=./cutover.py;
    environment.etc."cutover-fixture/system_control.py".source=./system_control.py;
    environment.etc."synthetic-generation".text="previous";
    systemd.services.mrjam-rust-blue={
      wantedBy=["multi-user.target"];
      serviceConfig={Type="simple";ExecStart="${pkgs.coreutils}/bin/sleep infinity";};
    };
    specialisation.staged.configuration={
      imports=[ ./boot-guard.nix ];
      environment.etc."synthetic-generation".text=lib.mkForce "staged";
      systemd.services.mrjam-rust-blue.wantedBy=lib.mkForce [];
    };
    specialisation.promoted.configuration={
      imports=[ ./boot-guard.nix ];
      environment.etc."synthetic-generation".text=lib.mkForce "promoted";
    };
  };
  testScript=''
    import json,os,shlex
    from pathlib import Path
    machine.start(allow_reboot=True)
    machine.wait_for_unit("multi-user.target")
    checks=[]
    roots={"previous":machine.succeed("readlink -f /run/current-system").strip(),
           "staged":machine.succeed("readlink -f /run/current-system/specialisation/staged").strip(),
           "promoted":machine.succeed("readlink -f /run/current-system/specialisation/promoted").strip()}
    machine.succeed("printf %s "+shlex.quote(json.dumps(roots))+" > /run/synthetic-generations.json")
    machine.succeed("install -d -m0700 /var/lib/mrjam-cutover /var/lib/mrjam-cutover/first-deployment")
    command="python3 ${operation} "
    with subtest("boot selection precedes any live generation change"):
        machine.succeed(command+"stage-boot",timeout=180)
        assert machine.succeed("cat /etc/synthetic-generation").strip()=="previous"
        machine.succeed("systemctl is-active --quiet mrjam-rust-blue")
        checks.append("select-staged-boot-with-previous-still-running")
    with subtest("reboot during freeze selects staged with writers held"):
        machine.reboot()
        machine.wait_for_unit("multi-user.target")
        assert machine.succeed("readlink -f /run/current-system").strip()==roots["staged"]
        assert machine.succeed("cat /etc/synthetic-generation").strip()=="staged"
        machine.fail("systemctl start mrjam-rust-blue")
        machine.succeed("printf %s "+shlex.quote(json.dumps(roots))+" > /run/synthetic-generations.json")
        checks.append("reboot-staged-and-pending-writer-mask")
    with subtest("explicit return restores the previous boot and configuration"):
        machine.succeed(command+"return-private",timeout=240)
        assert machine.succeed("cat /etc/synthetic-generation").strip()=="previous"
        machine.fail("systemctl start mrjam-rust-blue")
        machine.reboot()
        machine.wait_for_unit("multi-user.target")
        assert machine.succeed("readlink -f /run/current-system").strip()==roots["staged"]
        machine.fail("systemctl start mrjam-rust-blue")
        machine.succeed("printf %s "+shlex.quote(json.dumps(roots))+" > /run/synthetic-generations.json")
        checks.append("interrupted-private-return-reboots-guarded-staged")
        machine.succeed(command+"return",timeout=240)
        machine.succeed("systemctl daemon-reload; systemctl start mrjam-rust-blue")
        machine.reboot()
        machine.wait_for_unit("multi-user.target")
        assert machine.succeed("readlink -f /run/current-system").strip()==roots["previous"]
        machine.succeed("systemctl is-active --quiet mrjam-rust-blue")
        machine.succeed("printf %s "+shlex.quote(json.dumps(roots))+" > /run/synthetic-generations.json")
        checks.append("return-restores-previous-boot-and-live-generation")
    with subtest("promoted default boots only with durable completed opening"):
        machine.succeed(command+"promote",timeout=240)
        machine.succeed("systemctl daemon-reload; systemctl start mrjam-rust-blue")
        machine.reboot()
        machine.wait_for_unit("multi-user.target")
        assert machine.succeed("readlink -f /run/current-system").strip()==roots["promoted"]
        assert machine.succeed("cat /etc/synthetic-generation").strip()=="promoted"
        machine.succeed("systemctl is-active --quiet mrjam-rust-blue")
        checks.append("promoted-boot-after-durable-opening")
    Path(os.environ["out"],"result.json").write_text(json.dumps({
      "schema_version":1,"checks":checks,"production_access":False,
      "generation_sha256":"${builtins.hashFile "sha256" ./generation.py}",
      "system_control_sha256":"${builtins.hashFile "sha256" ./system_control.py}",
      "guard":"${guard}",
      "fixture_sha256":"${builtins.hashFile "sha256" ./generation-systemd.nix}",
      "limits":["Synthetic NixOS generations and inert application process", "Application adoption is qualified separately"]
    },sort_keys=True)+"\n")
  '';
}
