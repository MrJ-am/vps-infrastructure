{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  observer = pkgs.callPackage ./package.nix { };
  confinement = pkgs.writeText "synthetic-observer-confinement.py" ''
    import json, os, socket
    checks = {}
    for path in ("/var/lib/synthetic-observer-private", "/run/credentials/synthetic-observer-private", "/etc/shadow"):
        try:
            with open(path, "rb") as stream:
                stream.read(1)
            checks[path] = False
        except OSError:
            checks[path] = True
    try:
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.close()
        checks["inet-refused"] = False
    except OSError:
        checks["inet-refused"] = True
    try:
        with open("/etc/synthetic-observer-write", "wb") as stream:
            stream.write(b"synthetic")
        checks["system-write-refused"] = False
    except OSError:
        checks["system-write-refused"] = True
    assert all(checks.values()), checks
    print("CONFINEMENT_PASSED")
  '';
  confinementLauncher = pkgs.writeText "synthetic-observer-confinement-launch.py" ''
    import json, subprocess, sys
    sys.path.insert(0, "${observer}/libexec")
    import observe
    runtime = json.load(open("${observer}/libexec/runtime.json"))
    command = observe.command(runtime)
    command[command.index("--unit=mrjam-observe-services")] = "--unit=synthetic-observer-confinement"
    command[-1] = "${confinement}"
    raise SystemExit(subprocess.run(command, env=observe.ENVIRONMENT).returncode)
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-services-observation-synthetic";
  requiredFeatures.kvm = false; qemu.forceAccel = false; globalTimeout = 900;
  nodes.machine = { pkgs, ... }: {
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1024; virtualisation.cores = 2;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    users.groups.forgejo.gid = 977;
    users.users.forgejo = { uid = 977; isSystemUser = true; group = "forgejo"; };
    systemd.services.forgejo = {
      wantedBy = [ "multi-user.target" ];
      serviceConfig = { User = "forgejo"; Group = "forgejo"; ExecStart = "${pkgs.coreutils}/bin/sleep infinity"; };
    };
    environment.systemPackages = [ observer pkgs.python3 pkgs.util-linux ];
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("forgejo.service")
    checks = []
    with subtest("fixed root entry observes selected process metadata across Unix identities"):
        observed = json.loads(machine.succeed("mrjam-observe-services"))
        assert observed["schema_version"] == 1
        assert observed["authority"] == "unverified_observation"
        assert observed["accounts"]["forgejo"] == {"state":"observed", "uid":977, "gid":977}
        assert observed["accounts"]["kanidm"]["state"] == "absent"
        forgejo = observed["services"]["forgejo"]
        assert forgejo["state"] == "active"
        assert forgejo["executable"] == "${pkgs.coreutils}/bin/coreutils", observed
        assert forgejo["store_path"] == "${pkgs.coreutils}"
        assert forgejo["nar_hash"] is not None, observed
        assert observed["generation"]["nar_hash"] is not None, observed
        checks.append("real-systemd-cross-uid-executable-and-nar-metadata")

    with subtest("argument, unprivileged caller and mutable-copy entrypoints are refused"):
        machine.fail("mrjam-observe-services arbitrary-command > /tmp/argument-output")
        machine.fail("runuser -u forgejo -- mrjam-observe-services > /tmp/unprivileged-output")
        machine.succeed("cp -r ${observer}/libexec /tmp/observer-mutable")
        machine.fail("python3 -I -S /tmp/observer-mutable/observe.py > /tmp/mutable-output")
        machine.succeed("test ! -s /tmp/argument-output; test ! -s /tmp/unprivileged-output; test ! -s /tmp/mutable-output")
        machine.fail("systemctl is-active --quiet mrjam-observe-services.service")
        checks.append("arguments-unprivileged-and-mutable-entrypoints-refused-without-report")

    with subtest("unit collision cannot be used to substitute an observation"):
        machine.succeed("systemd-run --unit=mrjam-observe-services --property=Type=exec -- ${pkgs.coreutils}/bin/sleep infinity")
        machine.fail("mrjam-observe-services > /tmp/collision-output")
        machine.succeed("test ! -s /tmp/collision-output; systemctl stop mrjam-observe-services.service")
        checks.append("existing-unit-collision-refused")

    with subtest("exact sandbox properties deny data files, credentials, networking and system writes"):
        machine.succeed("printf SYNTHETIC-PRIVATE > /var/lib/synthetic-observer-private")
        machine.succeed("mkdir -p /run/credentials; printf SYNTHETIC-PRIVATE > /run/credentials/synthetic-observer-private")
        assert machine.succeed("python3 -I -S ${confinementLauncher}").strip() == "CONFINEMENT_PASSED"
        machine.fail("test -e /etc/synthetic-observer-write")
        checks.append("kernel-enforced-file-network-and-write-denials")

    with subtest("stopped service is reported without inventing a current executable"):
        machine.succeed("systemctl stop forgejo.service")
        observed = json.loads(machine.succeed("mrjam-observe-services"))
        assert observed["services"]["forgejo"]["state"] == "inactive"
        assert observed["services"]["forgejo"]["executable"] is None
        checks.append("stopped-service-keeps-build-unknown")

    Path(os.environ["out"], "services-observer-result.json").write_text(json.dumps({
        "schema_version":1, "scope":"synthetic-nixos-vm-tcg", "checks":checks,
        "production_access":False, "observation_package":"${observer}",
        "limitations":["Synthetic sleep process named forgejo, not Forgejo software", "NAR metadata is queried, not an authenticated attestation of running code", "Human bootstrap only; existing inventory SSH interface unchanged"]
    }, sort_keys=True)+"\n")
  '';
}
