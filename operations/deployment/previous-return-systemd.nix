# Targeted regression: real previous timer names/Unit=, invented jobs and state.
{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  guard = import ./boot-guard-package.nix { inherit pkgs; };
  modules = [ "release_backend" "cutover" "generation" "snapshot" "system_control" "stage_adoption" "stage_credentials" ];
  record = pkgs.writeText "previous-return-invented-job.py" ''
    import json,subprocess,sys
    from pathlib import Path
    phase=json.loads(Path("/var/lib/mrjam-cutover/first-deployment/phase.json").read_text())
    assert phase["phase"]=="previous-generation-restored"
    gate=subprocess.run(["${pkgs.nftables}/bin/nft","list","table","inet","mrjam_first_cutover"],capture_output=True)
    assert gate.returncode!=0,"A periodic job ran with external traffic closed"
    with Path("/run/return-"+sys.argv[1]).open("a") as stream:stream.write("returned-network-open\n")
  '';
  job = name: {
    serviceConfig = { Type="oneshot"; ExecStart="${pkgs.python3}/bin/python3 ${record} ${name}"; };
  };
  operation = pkgs.writeText "previous-return-regression.py" ''
    import json,os,sys
    from pathlib import Path
    from types import SimpleNamespace
    sys.path.insert(0,"/etc/return-fixture")
    from release_backend import Backend,Refused,RETURN_OPTIONAL
    from system_control import SystemControl,ALLOWED
    from cutover import Checkpoint,Phase
    state=Path("/var/lib/mrjam-cutover/first-deployment")
    state.mkdir(mode=0o700,parents=True)
    checkpoint=Checkpoint(state)
    checkpoint.write(Phase.RETURNING,1)
    volatile=Path("/run/mrjam-cutover")
    volatile.mkdir(mode=0o700)
    raw=Path("/proc/self/stat").read_bytes()
    ticks=raw[raw.rfind(b")")+2:].split()[19].decode()
    lease=volatile/"active.json"
    lease.write_text(json.dumps({"pid":os.getpid(),"start_ticks":ticks}));lease.chmod(0o600)
    control=SystemControl("${pkgs.systemd}/bin/systemctl","${pkgs.nftables}/bin/nft","${guard}/bin/mrjam-first-cutover-guard")
    control.observe()
    assert "mrjam-kanidm-backup.service" in control.foreign_masks
    control.active_before={"acme-renew-audition.mrj.am.timer","forgejo-backup.timer",
        "acme-setup.service","acme-audition.mrj.am.service","acme-log.mrj.am.service",
        "forgejo-backup.service","vision-cycle.service"}|set(RETURN_OPTIONAL)
    control.close_ingress()
    control.masked_here=set(ALLOWED)-control.foreign_masks
    control.publish_masks()
    control.execute([control.systemctl,"daemon-reload"])
    control.verify_masks()
    backend=object.__new__(Backend)
    backend.control=control;backend.checkpoint=checkpoint
    backend.original={"foreign_masks":sorted(control.foreign_masks)}
    def select(target):
        assert checkpoint.read()==Phase.RETURNED and target=="invented-previous"
        Path("/run/return-boot-selected").touch()
    backend.generations=SimpleNamespace(previous="invented-previous",select_boot=select)
    try:backend.reopen_previous_services()
    except Refused as exc:assert str(exc)=="DURABLE_RETURNED_REQUIRED"
    else:raise AssertionError("Reopened before RETURNED")
    assert not Path("/run/return-boot-selected").exists()
    assert control.gate_created
    checkpoint.write(Phase.RETURNED,2)
    backend.reopen_previous_services()
    assert not control.gate_created
    assert control.properties("acme-renew-audition.mrj.am.timer")["ActiveState"]=="active"
    assert control.properties("forgejo-backup.timer")["ActiveState"]=="active"
    assert control.properties("acme-log.mrj.am.service")["LoadState"]=="masked"
    assert control.properties("mrjam-kanidm-backup.service")["LoadState"]=="masked"
    for unit in RETURN_OPTIONAL:assert control.properties(unit)["LoadState"]=="masked"
    Path("/run/return-method-passed").touch()
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-previous-return-nonstem-timers";
  requiredFeatures.kvm = true;
  globalTimeout = 300;
  nodes.machine = { ... }: {
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1024;
    virtualisation.cores = 1;
    virtualisation.vlans = [];
    environment.systemPackages = [ pkgs.python3 pkgs.nftables ];
    environment.etc = builtins.listToAttrs (map (name: {
      name="return-fixture/${name}.py"; value.source=./. + "/${name}.py";
    }) modules);
    systemd.services = {
      "acme-setup" = job "acme-setup";
      "acme-audition.mrj.am" = (job "acme-domain") // {
        requires=[ "acme-setup.service" ]; after=[ "acme-setup.service" ];
      };
      "acme-order-renew-audition.mrj.am" = (job "acme-order") // {
        requires=[ "acme-audition.mrj.am.service" ]; after=[ "acme-audition.mrj.am.service" ];
      };
      "acme-log.mrj.am" = job "forbidden-direct-acme";
      "forgejo-backup" = job "backup";
      "vision-cycle" = job "worker";
      "vise" = job "forbidden-vise";
      "vise-provision" = job "forbidden-vise-provision";
      "mrjam-kanidm-backup".enable = false;
    };
    systemd.timers = {
      "acme-renew-audition.mrj.am".timerConfig = {
        Unit="acme-order-renew-audition.mrj.am.service"; OnActiveSec="1s"; AccuracySec="100ms";
      };
      "forgejo-backup".timerConfig = { OnActiveSec="1s"; AccuracySec="100ms"; };
    };
  };
  testScript = ''
    import json,os
    from pathlib import Path
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.succeed("python3 ${operation}",timeout=180)
    for name in ("acme-setup","acme-domain","acme-order","backup","worker"):
        machine.wait_for_file("/run/return-"+name)
        assert machine.succeed("cat /run/return-"+name).strip()=="returned-network-open"
    machine.succeed("test -e /run/return-method-passed")
    for name in ("forbidden-direct-acme","forbidden-vise","forbidden-vise-provision"):
        machine.succeed("test ! -e /run/return-"+name)
    machine.succeed("systemctl daemon-reload")
    machine.fail("systemctl start vise.service")
    machine.fail("systemctl start mrjam-kanidm-backup.service")
    Path(os.environ["out"],"result.json").write_text(json.dumps({
      "schema_version":1,"passed":True,"production_access":False,
      "checks":["durable-returned-required-before-opening", "real-nonstem-timer-target-and-acme-dependencies",
                "scheduled-jobs-run-after-network-opening", "no-direct-acme-or-vise-replay-and-foreign-mask-preserved"],
      "backend_sha256":"${builtins.hashFile "sha256" ./release_backend.py}",
      "control_sha256":"${builtins.hashFile "sha256" ./system_control.py}",
      "fixture_sha256":"${builtins.hashFile "sha256" ./previous-return-systemd.nix}",
      "guard":"${guard}",
      "limits":["Only reopen_previous_services is exercised; generation selection is an explicit assertion fixture.",
                "Real systemd timers, early masks, dependencies and nft gate; invented jobs record phase and gate state.",
                "No production access, real ACME issuance, mail, backup contents or application data."]
    },sort_keys=True)+"\n")
  '';
}
