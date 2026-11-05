# Exercise real NixOS/systemd boundaries in a disposable VM, never the VPS.
{ pkgs ? import ../forgejo/locked-toolchain.nix {} }:
let
  engine = import ./package.nix { inherit pkgs; };
  controls = import ./services.nix { inherit pkgs; };
  activate = pkgs.writeText "delivery-activate.py" ''
    import sys
    sys.path.insert(0, '${engine}/operations/continuous-delivery')
    import system_delivery
    import deploy, subprocess
    def command(arguments, timeout=30):
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            print(result.stdout, flush=True)
            print(result.stderr, flush=True)
        result.check_returncode()
        return result.stdout.strip()
    deploy.command = command
    system_delivery.activate(sys.argv[1])
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-delivery-activation";
  nodes.machine = { lib, ... }: {
    # The test driver boots its kernel directly; like NixOS's switch-test,
    # exercise activation without installing GRUB on its unpartitioned disk.
    boot.loader.grub.enable = false;
    virtualisation.memorySize = 1536;
    virtualisation.cores = 2;
    environment.systemPackages = [ pkgs.python3 pkgs.nix ];
    systemd.services.fixture-app = {
      wantedBy = [ "multi-user.target" ];
      after = [ "mrjam-delivery-restore.service" ];
      unitConfig.ConditionPathExists = "/run/mrjam-delivery-restored";
      restartIfChanged = false;
      stopIfChanged = false;
      serviceConfig.ExecStart = "${pkgs.coreutils}/bin/sleep infinity";
    };
    specialisation.updated.configuration = {
      environment.etc."mrjam-ci/engine".source = engine;
      environment.etc."delivery-generation".text = "updated";
    };
    system.stateVersion = "26.05";
  };
  testScript = ''
    start_all()
    machine.wait_for_unit("multi-user.target")
    old = machine.succeed("readlink -f /run/current-system").strip()
    new = machine.succeed("readlink -f /run/current-system/specialisation/updated").strip()
    machine.succeed("mkdir -p /var/lib/mrjam-delivery /etc/mrjam-ci /etc/nginx /etc/systemd/system.control/multi-user.target.wants")
    machine.succeed("ln -s ${engine} /var/lib/mrjam-delivery/engine")
    machine.succeed("printf synthetic-test-token > /etc/mrjam-ci/source-token")
    for name in ["mrjam-delivery", "mrjam-delivery-restore"]:
        machine.succeed(f"ln -s ${controls}/{name}.service /etc/systemd/system.control/{name}.service")
        machine.succeed(f"ln -s /etc/systemd/system.control/{name}.service /etc/systemd/system.control/multi-user.target.wants/{name}.service")
    machine.succeed("systemctl daemon-reload; systemctl start mrjam-delivery-restore mrjam-delivery fixture-app")
    machine.wait_for_unit("fixture-app.service")
    machine.wait_for_unit("mrjam-delivery.service")
    app_pid = machine.succeed("systemctl show fixture-app -p MainPID --value").strip()
    watcher_pid = machine.succeed("systemctl show mrjam-delivery -p MainPID --value").strip()
    machine.succeed(f"python3 ${activate} {new}")
    machine.succeed("test -f /etc/delivery-generation; test -e /etc/mrjam-ci/engine")
    machine.succeed(f"python3 ${activate} {old}")
    machine.succeed("test ! -e /etc/mrjam-ci/engine; test -e /var/lib/mrjam-delivery/engine; test -e /run/mrjam-delivery-restored")
    assert machine.succeed("systemctl show fixture-app -p MainPID --value").strip() == app_pid
    assert machine.succeed("systemctl show mrjam-delivery -p MainPID --value").strip() == watcher_pid
    # A runtime restart of the boot restoration must neither stop the app nor
    # run recovery against an in-flight transaction. Its boot marker skips it.
    machine.succeed("printf '{invalid fixture journal' > /var/lib/mrjam-delivery/transaction.json")
    machine.succeed("systemctl restart mrjam-delivery-restore")
    assert machine.succeed("systemctl show fixture-app -p MainPID --value").strip() == app_pid
    machine.succeed("test -e /var/lib/mrjam-delivery/transaction.json; rm /var/lib/mrjam-delivery/transaction.json")
    # At boot the marker is absent: restoration must finish before the app starts.
    machine.shutdown()
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("fixture-app.service")
    machine.wait_for_unit("mrjam-delivery.service")
    machine.succeed("test -e /run/mrjam-delivery-restored; test -e /var/lib/mrjam-delivery/engine")
  '';
}
