# Invented listeners and a virtual Ethernet namespace; no external NIC/network.
{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  guard = import ./boot-guard-package.nix { inherit pkgs; };
  listener = pkgs.writeText "synthetic-listeners.py" ''
    import socketserver,sys,threading
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.sendall(b"synthetic\n")
    for port in map(int, sys.argv[1:]):
        server=socketserver.ThreadingTCPServer(("0.0.0.0",port), Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
    threading.Event().wait()
  '';
  fixture = pkgs.writeText "synthetic-system-boundary.py" ''
    import json,os,subprocess,sys,time
    from pathlib import Path
    sys.path.insert(0,"/etc/cutover-test")
    from system_control import SystemControl,Refused
    from cutover import Checkpoint,Phase
    import boot_guard
    def run(argv,success=True):
        r=subprocess.run(argv,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
        assert (r.returncode==0)==success,"SYNTHETIC_BOUNDARY_FAILURE"
    IP="${pkgs.iproute2}/bin/ip"
    NC="${pkgs.netcat-openbsd}/bin/nc"
    SYSTEMCTL="${pkgs.systemd}/bin/systemctl"
    GUARD="${guard}/bin/mrjam-first-cutover-guard"
    def transaction(phase):
        parent=Path("/var/lib/mrjam-cutover/first-deployment")
        parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        checkpoint=Checkpoint(parent)
        checkpoint.write(phase,1)
        live=Path("/run/mrjam-cutover")
        live.mkdir(mode=0o700,exist_ok=True)
        raw=Path("/proc/self/stat").read_bytes()
        ticks=raw[raw.rfind(b")")+2:].split()[19].decode()
        path=live/"active.json"
        path.write_text(json.dumps({"pid":os.getpid(),"start_ticks":ticks}))
        path.chmod(0o600)
        return checkpoint
    case=sys.argv[1]
    if case=="network":
        run([IP,"netns","add","synthetic-peer"])
        run([IP,"link","add","cutover-host","type","veth","peer","name","cutover-peer"])
        run([IP,"link","set","cutover-peer","netns","synthetic-peer"])
        run([IP,"addr","add","10.77.0.1/24","dev","cutover-host"])
        run([IP,"link","set","cutover-host","up"])
        run([IP,"netns","exec","synthetic-peer",IP,"addr","add","10.77.0.2/24","dev","cutover-peer"])
        run([IP,"netns","exec","synthetic-peer",IP,"link","set","cutover-peer","up"])
        run([SYSTEMCTL,"start","synthetic-peer-listener.service"])
        outside=[IP,"netns","exec","synthetic-peer",NC,"-z","-w","1"]
        app=["${pkgs.util-linux}/bin/runuser","-u","synthetic-forge","--",NC,"-z","-w","1"]
        for port in (22,80,443,2222):run(outside+["10.77.0.1",str(port)])
        run(app+["10.77.0.2","587"])
        checkpoint=transaction(Phase.PREPARED)
        control=SystemControl(SYSTEMCTL,"${pkgs.nftables}/bin/nft",GUARD)
        control.observe()
        assert "vise.service" in control.foreign_masks
        control.close_ingress()
        for port in (80,443,2222):run(outside+["10.77.0.1",str(port)],False)
        run(outside+["10.77.0.1","22"])
        run([NC,"-z","-w","1","127.0.0.1","443"])
        run(app+["10.77.0.2","587"],False)
        run(app+["127.0.0.1","80"])
        # A firewall reload boundary is re-established without touching a
        # separate table owned by another component.
        run(["${pkgs.nftables}/bin/nft","add","table","inet","synthetic_preserved"])
        control.close_ingress()
        run(["${pkgs.nftables}/bin/nft","list","table","inet","synthetic_preserved"])
        control.freeze()
        assert control.properties("mrjam-rust-blue.service")["ActiveState"]=="inactive"
        assert control.properties("mrjam-rust-blue.service")["LoadState"]=="masked"
        run([SYSTEMCTL,"start","mrjam-rust-blue.service"],False)
        run([SYSTEMCTL,"start","postgresql.service"],False)
        run([SYSTEMCTL,"daemon-reload"])
        run([SYSTEMCTL,"start","mrjam-rust-blue.service"],False)
        run([SYSTEMCTL,"daemon-reexec"])
        run([SYSTEMCTL,"start","mrjam-rust-blue.service"],False)
        control.start(["postgresql.service"])
        assert control.properties("postgresql.service")["ActiveState"]=="active"
        run([SYSTEMCTL,"start","mrjam-rust-blue.service"],False)
        control.start(["mrjam-rust-blue.service"])
        assert control.properties("mrjam-rust-blue.service")["ActiveState"]=="active"
        control.open_ingress()
        for port in (22,80,443,2222):run(outside+["10.77.0.1",str(port)])
        run(app+["10.77.0.2","587"])
        # Remove only this transaction's masks before the generator test.
        control.release_masks(tuple(control.masked_here))
        assert control.properties("vise.service")["LoadState"]=="masked"
        checkpoint.write(Phase.OPEN,20)
    elif case=="live":
        transaction(Phase.ADOPTED)
        assert not boot_guard.must_hold()
        run([SYSTEMCTL,"daemon-reload"])
        run([SYSTEMCTL,"restart","mrjam-rust-blue.service"])
        # Deliberately leave a stale lease, simulating a terminated process.
    elif case=="stale":
        assert boot_guard.must_hold()
        run([SYSTEMCTL,"daemon-reload"])
        run([SYSTEMCTL,"stop","mrjam-rust-blue.service"])
        run([SYSTEMCTL,"start","mrjam-rust-blue.service"],False)
    elif case=="open":
        Checkpoint("/var/lib/mrjam-cutover/first-deployment").write(Phase.OPEN,20)
        run([SYSTEMCTL,"daemon-reload"])
        run([SYSTEMCTL,"start","mrjam-rust-blue.service"])
    elif case=="malformed":
        Path("/var/lib/mrjam-cutover/first-deployment/phase.json").write_text("PRIVATE_MALFORMED")
        run([SYSTEMCTL,"daemon-reload"])
        run([SYSTEMCTL,"stop","mrjam-rust-blue.service"])
        run([SYSTEMCTL,"start","mrjam-rust-blue.service"],False)
    elif case=="malformed-masks":
        Checkpoint("/var/lib/mrjam-cutover/first-deployment").write(Phase.OPEN,20)
        folder=Path("/run/mrjam-cutover")
        folder.mkdir(mode=0o700,exist_ok=True)
        path=folder/"masks.json"
        path.write_text('{"schema_version":1,"units":["sshd.service"]}')
        path.chmod(0o600)
        run([SYSTEMCTL,"daemon-reload"])
        run([SYSTEMCTL,"stop","mrjam-rust-blue.service"])
        run([SYSTEMCTL,"start","mrjam-rust-blue.service"],False)
    else:raise RuntimeError("FIXTURE_CASE_REFUSED")
    print(json.dumps({"case":case,"passed":True}))
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-cutover-network-and-boot-guard";
  requiredFeatures.kvm = true;
  globalTimeout = 900;
  nodes.machine = { lib, ... }: {
    imports = [ ./boot-guard.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 768;
    virtualisation.cores = 2;
    virtualisation.vlans = [ ];
    networking.firewall.enable = false;
    services.openssh.enable = true;
    users.groups.synthetic-forge.gid = 982;
    users.users.synthetic-forge = { isSystemUser=true;uid=982;group="synthetic-forge"; };
    environment.etc."cutover-test/system_control.py".source = ./system_control.py;
    environment.etc."cutover-test/boot_guard.py".source = ./boot_guard.py;
    environment.etc."cutover-test/cutover.py".source = ./cutover.py;
    systemd.services.synthetic-listeners = {
      wantedBy=[ "multi-user.target" ];
      serviceConfig.ExecStart="${pkgs.python3}/bin/python3 ${listener} 80 443 2222";
    };
    systemd.services.synthetic-peer-listener.serviceConfig.ExecStart = "${pkgs.iproute2}/bin/ip netns exec synthetic-peer ${pkgs.python3}/bin/python3 ${listener} 587";
    systemd.services.mrjam-rust-blue = {
      wantedBy = [ "multi-user.target" ];
      serviceConfig = { Type="oneshot"; RemainAfterExit=true; ExecStart="${pkgs.coreutils}/bin/touch /run/synthetic-writer-started"; };
    };
    systemd.services.postgresql.serviceConfig = { Type="oneshot"; RemainAfterExit=true; ExecStart="${pkgs.coreutils}/bin/true"; };
    systemd.services.vise.enable = false;
  };
  testScript = ''
    import json,os
    from pathlib import Path
    machine.start(allow_reboot=True)
    machine.wait_for_unit("sshd.service")
    machine.wait_for_unit("synthetic-listeners.service")
    machine.wait_for_unit("mrjam-rust-blue.service")
    checks=[]
    command="${pkgs.python3}/bin/python3 ${fixture} "
    for case in ("network","live","stale"):
        with subtest(case):
            assert json.loads(machine.succeed(command+case,timeout=240))=={"case":case,"passed":True}
            checks.append(case)
    with subtest("pending transaction cannot restart writers after reboot; SSH survives"):
        machine.reboot()
        machine.wait_for_unit("sshd.service")
        machine.fail("systemctl start mrjam-rust-blue.service")
        machine.fail("test -e /run/synthetic-writer-started")
        checks.append("reboot-holds-writers-keeps-ssh")
    for case in ("open","malformed","malformed-masks"):
        with subtest(case):
            assert json.loads(machine.succeed(command+case))=={"case":case,"passed":True}
            checks.append(case)
    Path(os.environ["out"],"result.json").write_text(json.dumps({
        "schema_version":1,"checks":checks,"production_access":False,
        "system_control_sha256":"${builtins.hashFile "sha256" ./system_control.py}",
        "boot_guard_sha256":"${builtins.hashFile "sha256" ./boot_guard.py}",
        "limits":["Synthetic listeners and network namespace only", "No actual generation switch"]
    },sort_keys=True)+"\n")
  '';
}
