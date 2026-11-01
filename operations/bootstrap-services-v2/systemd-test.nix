{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  observer = pkgs.callPackage ./package.nix { };
  legacy = pkgs.callPackage ../bootstrap-services/package.nix { };
  launcher = pkgs.writeText "synthetic-observer-v2-probe-launch.py" ''
    import importlib.util, json, subprocess, sys, time
    from pathlib import Path
    sys.path.insert(0, "${observer}/libexec")
    import observe
    runtime = json.loads(Path("${observer}/libexec/runtime.json").read_text())
    mode = sys.argv[1]
    assert mode in ("legacy", "seccomp", "full", "no-landlock", "broker-control", "broker")
    command = observe.command(runtime)
    if mode == "legacy":
        spec = importlib.util.spec_from_file_location("legacy", "${legacy}/libexec/observe.py")
        original = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(original)
        command = original.command(runtime)
    if mode == "broker-control":
        # Causal control differs only by removing V2's explicit syscall deny
        # list. Retain EPERM: V1's default SIGSYS would kill this test on calls
        # already outside @system-service, before it can report the result.
        command = [item for item in command if not item.startswith("--property=SystemCallFilter=~")]
    unit = "synthetic-observer-v2-" + mode
    command[command.index("--unit=mrjam-observe-services")] = "--unit=" + unit
    if mode == "no-landlock":
        command.insert(command.index("--"), "--property=SystemCallFilter=~landlock_create_ruleset")
        run = subprocess.run(command, env=observe.ENVIRONMENT, capture_output=True, timeout=60)
        assert run.returncode != 0 and run.stdout == b"", (run.returncode, run.stdout)
        print("LANDLOCK_UNAVAILABLE_REFUSED")
        raise SystemExit(0)
    pid, address = Path("/run/services-v2-synthetic-victim/metadata").read_text().split()
    root_pid, root_address = Path("/run/services-v2-synthetic-root/metadata").read_text().split()
    assert all(value.isdigit() for value in (pid, address, root_pid, root_address))
    if mode.startswith("broker"):
        payload = ["${observer.tests}/bin/broker-probe", "0" if mode == "broker-control" else "1"]
    else:
        payload = ["${observer.tests}/bin/confinement-probe", str(("legacy", "seccomp", "full").index(mode))]
    command = command[:command.index("--")+1] + payload + [pid, address, root_pid, root_address]
    # Only the unit name and payload differ from the real collector. The full
    # payload invokes the very same compiled confinement.o as collect-confined.
    child = subprocess.Popen(command, env=observe.ENVIRONMENT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    properties = {}
    for _ in range(100):
        result = subprocess.run([runtime["systemctl"], "show", unit+".service",
            "--property=ActiveState,User,Group,NoNewPrivileges,MemoryMax,TasksMax,CPUQuotaPerSecUSec,RuntimeMaxUSec,LimitNOFILE,CapabilityBoundingSet,AmbientCapabilities"],
            env=observe.ENVIRONMENT, capture_output=True, text=True, timeout=10)
        properties = dict(line.split("=",1) for line in result.stdout.splitlines())
        if properties.get("ActiveState") == "active" or child.poll() is not None:
            break
        time.sleep(0.1)
    out, errors = child.communicate(timeout=90)
    assert child.returncode == 0, (child.returncode, out.decode(), errors.decode())
    for key, expected in {"ActiveState":"active", "User":"root", "Group":"root",
        "NoNewPrivileges":"yes", "MemoryMax":"268435456", "TasksMax":"16",
        "CPUQuotaPerSecUSec":"250ms", "RuntimeMaxUSec":"2min", "LimitNOFILE":"64",
        "CapabilityBoundingSet":"cap_sys_ptrace", "AmbientCapabilities":"cap_sys_ptrace"}.items():
        assert properties.get(key) == expected, (key, properties)
    print(out.decode(), end="")
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-services-observation-v2-synthetic";
  requiredFeatures.kvm = false; qemu.forceAccel = false; globalTimeout = 1200;
  nodes.machine = { pkgs, ... }: {
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1024; virtualisation.cores = 2;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    users.groups.forgejo.gid = 977;
    users.users.forgejo = { uid = 977; isSystemUser = true; group = "forgejo"; };
    systemd.services.forgejo = {
      wantedBy = [ "multi-user.target" ];
      environment.SYNTHETIC_TEST_ENV = "SYNTHETIC_ENV_ONLY";
      serviceConfig = { User = "forgejo"; Group = "forgejo";
        RuntimeDirectory = "services-v2-synthetic-victim"; RuntimeDirectoryMode = "0700";
        ExecStart = "${observer.tests}/bin/synthetic-victim SYNTHETIC_ARG_ONLY"; };
    };
    systemd.services.synthetic-root-victim = {
      wantedBy = [ "multi-user.target" ];
      environment.SYNTHETIC_TEST_ENV = "SYNTHETIC_ENV_ONLY";
      serviceConfig = { User = "root"; Group = "root";
        CapabilityBoundingSet = ""; AmbientCapabilities = ""; NoNewPrivileges = true;
        RuntimeDirectory = "services-v2-synthetic-root"; RuntimeDirectoryMode = "0700";
        ExecStart = "${observer.tests}/bin/synthetic-victim root SYNTHETIC_ARG_ONLY"; };
    };
    environment.systemPackages = [ observer pkgs.python3 pkgs.util-linux ];
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("forgejo.service")
    machine.wait_for_file("/run/services-v2-synthetic-victim/metadata")
    machine.wait_for_unit("synthetic-root-victim.service")
    machine.wait_for_file("/run/services-v2-synthetic-root/metadata")
    checks = []
    machine.succeed("printf SYNTHETIC-PRIVATE > /var/lib/synthetic-observer-private")
    machine.succeed("mkdir -p /run/credentials; printf SYNTHETIC-PRIVATE > /run/credentials/synthetic-observer-private")

    with subtest("V1 positive control reproduces memory exposure with a foreign synthetic identity"):
        control = json.loads(machine.succeed("python3 -I -S ${launcher} legacy"))
        assert control["readlink_exe"] is True
        assert control["memory_syscalls_denied"] is False and control["proc_files_denied"] is False
        assert control["proc_aliases_checked"] is True
        assert control["private_files_network_and_writes_denied"] is True
        checks.append("v1-defect-reproduced-cross-uid-syscalls-and-same-uid-proc-sentinels")

    with subtest("seccomp blocks memory syscalls but proc contents remain accessible without Landlock"):
        control = json.loads(machine.succeed("python3 -I -S ${launcher} seccomp"))
        assert control["memory_syscalls_denied"] is True and control["proc_files_denied"] is False
        assert control["readlink_exe"] is True
        checks.append("seccomp-causal-control-separates-syscalls-from-proc-file-access")

    with subtest("exact V2 properties and shared Landlock code deny memory paths and keep exe metadata"):
        confined = json.loads(machine.succeed("python3 -I -S ${launcher} full"))
        assert confined == {"mode":2, "readlink_exe":True, "memory_syscalls_denied":True,
            "proc_files_denied":True, "proc_aliases_checked":True,
            "private_files_network_and_writes_denied":True, "proc_subject":"synthetic-root",
            "memory_syscall_subject":"synthetic-foreign-uid"}
        machine.fail("test -e /etc/synthetic-observer-write")
        checks.append("kernel-enforced-memory-proc-alias-file-network-and-write-denials-with-exe-readlink")
        checks.append("actual-root-capability-cgroup-limits-and-lifetime-match-production-properties")
        checks.append("reader-zero-capabilities-and-landlock-persist-after-exec")

    with subtest("unsupported or denied Landlock fails closed before the collector and any report"):
        assert machine.succeed("python3 -I -S ${launcher} no-landlock").strip() == "LANDLOCK_UNAVAILABLE_REFUSED"
        checks.append("landlock-unavailable-refused-without-report-or-degraded-fallback")

    with subtest("identical broker filter denies 24 operations, with positive controls and finite protocol"):
        for mode in ("broker-control", "broker"):
            broker = json.loads(machine.succeed("python3 -I -S ${launcher} " + mode))
            assert broker == {"broker_denials":24, "readlink_exe":True, "positive_controls":True,
                "malformed_protocol_refused":True, "request_limit":14}
        checks.append("broker-default-deny-24-syscall-probes-causal-controls-and-exe-readlink")
        checks.append("broker-private-protocol-malformed-requests-refused-and-14-request-limit")

    with subtest("shipped C entrypoint and collector observe only fixed identity and executable metadata"):
        observed = json.loads(machine.succeed("mrjam-observe-services"))
        assert observed["schema_version"] == 1 and observed["authority"] == "unverified_observation"
        assert observed["accounts"]["forgejo"] == {"state":"observed", "uid":977, "gid":977}
        assert observed["accounts"]["kanidm"]["state"] == "absent"
        forgejo = observed["services"]["forgejo"]
        assert forgejo["state"] == "active"
        assert forgejo["executable"] == "${observer.tests}/bin/synthetic-victim", observed
        assert forgejo["store_path"] == "${observer.tests}" and forgejo["nar_hash"] is not None, observed
        assert observed["generation"]["nar_hash"] is not None, observed
        assert "SYNTHETIC_" not in json.dumps(observed)
        checks.append("shipped-landlocked-collector-cross-uid-executable-identities-nar-and-filtering")

    with subtest("argument, unprivileged caller and mutable-copy entrypoints remain refused"):
        machine.fail("mrjam-observe-services arbitrary-command > /tmp/argument-output")
        machine.fail("runuser -u forgejo -- mrjam-observe-services > /tmp/unprivileged-output")
        machine.fail("${observer}/libexec/collect-confined arbitrary-command > /tmp/c-entry-output")
        machine.succeed("cp -r ${observer}/libexec /tmp/observer-mutable")
        machine.fail("python3 -I -S /tmp/observer-mutable/observe.py > /tmp/mutable-output")
        machine.succeed("test ! -s /tmp/argument-output; test ! -s /tmp/unprivileged-output; test ! -s /tmp/mutable-output; test ! -s /tmp/c-entry-output")
        machine.fail("systemctl is-active --quiet mrjam-observe-services.service")
        checks.append("arguments-unprivileged-and-mutable-entrypoints-refused-without-report")

    with subtest("unit collision cannot substitute an observation"):
        machine.succeed("systemd-run --unit=mrjam-observe-services --property=Type=exec -- ${pkgs.coreutils}/bin/sleep infinity")
        machine.fail("mrjam-observe-services > /tmp/collision-output")
        machine.succeed("test ! -s /tmp/collision-output; systemctl stop mrjam-observe-services.service")
        checks.append("existing-unit-collision-refused")

    with subtest("stopped service keeps its running build unknown"):
        machine.succeed("systemctl stop forgejo.service")
        observed = json.loads(machine.succeed("mrjam-observe-services"))
        assert observed["services"]["forgejo"]["state"] == "inactive"
        assert observed["services"]["forgejo"]["executable"] is None
        checks.append("stopped-service-keeps-build-unknown")

    Path(os.environ["out"], "services-observer-result.json").write_text(json.dumps({
        "schema_version":1, "scope":"synthetic-nixos-vm-tcg", "checks":checks,
        "production_access":False, "observation_package":"${observer}",
        "test_executables":"${observer.tests}", "systemd":"${pkgs.systemd.version}",
        "limitations":["Dedicated synthetic memory victim named forgejo, not Forgejo software",
            "Landlock ABI >=3 required; VPS support remains unobserved and absence must fail closed",
            "NAR metadata is not an authenticated attestation of running code",
            "Human bootstrap only; existing inventory SSH interface unchanged"]
    }, sort_keys=True)+"\n")
  '';
}
