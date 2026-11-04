# Narrow network qualification only. Invented users/listeners, no CI jobs,
# credentials, Forgejo data, application database or production access.
{ nixpkgs ? /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  lib = pkgs.lib;
  locked = import ../../forgejo/locked-toolchain.nix { };
  runner = import ../../nixos/mrjam-forgejo-runner.nix {
    inherit lib; pkgs = locked;
    config.services.mrjamForgejoRunner = { enable = true; coordinatorUid = 61001; registrarUid = 61002; };
  };
  # Select the actual qualified module's table, not a retyped approximation.
  table = assert runner.config._type == "if" && runner.config.condition;
    runner.config.content.networking.nftables.tables.mrjam-forgejo-coordinator;
  fixture = pkgs.writeText "ci-network-fixture.py" ''
    import socket, sys, threading
    if sys.argv[1] == 'connect':
        try:
            with socket.create_connection((sys.argv[2], int(sys.argv[3])), timeout=1) as sock:
                assert sock.recv(2) == b'OK'
        except (OSError, AssertionError):
            sys.exit(1)
    else:
        def serve(family, address, port):
            listener = socket.socket(family)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if family == socket.AF_INET6:
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            listener.bind((address, port)); listener.listen(8)
            while True:
                conn, _ = listener.accept()
                with conn: conn.sendall(b'OK')
        for family, address, port in [(socket.AF_INET, '0.0.0.0', 3004),
            (socket.AF_INET, '127.0.0.1', 3005), (socket.AF_INET6, '::1', 3004),
            (socket.AF_INET, '0.0.0.0', 80), (socket.AF_INET, '0.0.0.0', 8080)]:
            threading.Thread(target=serve, args=(family,address,port), daemon=True).start()
        threading.Event().wait()
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-ci-input-firewall-output-table-coexistence";
  requiredFeatures.kvm = true;
  globalTimeout = 600;
  nodes.machine = { ... }: {
    imports = [ ../preserve-input-firewall.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 768;
    virtualisation.cores = 2;
    virtualisation.vlans = [];
    networking.firewall.allowedTCPPorts = [ 22 80 443 2222 ];
    networking.nftables.tables.mrjam-forgejo-coordinator = table;
    users.groups.synthetic-coordinator.gid = 61001;
    users.groups.synthetic-registrar.gid = 61002;
    users.users.synthetic-coordinator = { isSystemUser = true; uid = 61001; group = "synthetic-coordinator"; };
    users.users.synthetic-registrar = { isSystemUser = true; uid = 61002; group = "synthetic-registrar"; };
    systemd.services.synthetic-listeners = {
      wantedBy = [ "multi-user.target" ];
      serviceConfig.ExecStart = "${pkgs.python3}/bin/python3 -I -S ${fixture} serve";
    };
    environment.systemPackages = [ pkgs.python3 pkgs.nftables pkgs.iptables pkgs.iproute2 pkgs.util-linux ];
  };
  testScript = ''
    import json, os
    from pathlib import Path
    start_all()
    machine.wait_for_unit('multi-user.target')
    machine.wait_for_unit('nftables.service')
    machine.wait_for_unit('firewall.service')
    command = '${pkgs.python3}/bin/python3 -I -S ${fixture} connect '
    machine.wait_until_succeeds(command + '127.0.0.1 3004')
    assert '(nf_tables)' in machine.succeed('iptables --version')
    machine.succeed('ip netns add synthetic-peer')
    machine.succeed('ip link add ci-host type veth peer name ci-peer')
    machine.succeed('ip link set ci-peer netns synthetic-peer')
    machine.succeed('ip addr add 192.0.2.1/30 dev ci-host')
    machine.succeed('ip link set ci-host up')
    machine.succeed('ip netns exec synthetic-peer ip addr add 192.0.2.2/30 dev ci-peer')
    machine.succeed('ip netns exec synthetic-peer ip link set ci-peer up')
    machine.succeed('ip netns exec synthetic-peer ip link set lo up')
    def ingress():
        machine.succeed('ip netns exec synthetic-peer ' + command + '192.0.2.1 80')
        machine.fail('ip netns exec synthetic-peer ' + command + '192.0.2.1 8080')
    def egress():
        for user in ('synthetic-coordinator','synthetic-registrar'):
            prefix='runuser -u '+user+' -- '+command
            machine.succeed(prefix+'127.0.0.1 3004')
            for target in ('127.0.0.1 3005', '::1 3004', '192.0.2.1 3004'):
                machine.succeed(command+target) # proves each fixture listener exists
                machine.fail(prefix+target)
    checks=[]
    with subtest('actual CI UID rules preserve input firewall'):
        ingress(); egress()
        checks.append('input-and-ci-output-enforced')
    machine.succeed('nft add table inet synthetic-foreign')
    machine.succeed('nft add chain inet synthetic-foreign preserved')
    before4=machine.succeed('iptables-save')
    before6=machine.succeed('ip6tables-save')
    def normal(text):
        return '\n'.join(line for line in text.splitlines() if not line.startswith('#'))
    with subtest('nft reload retains input and unrelated tables'):
        machine.succeed('systemctl reload nftables.service')
        assert normal(machine.succeed('iptables-save')) == normal(before4)
        assert normal(machine.succeed('ip6tables-save')) == normal(before6)
        machine.succeed('nft list chain inet synthetic-foreign preserved')
        ingress(); egress()
        checks.append('nft-reload-preserves-input-and-foreign-table')
    with subtest('input reload retains CI output and unrelated table'):
        machine.succeed('systemctl reload firewall.service')
        machine.succeed('nft list chain inet synthetic-foreign preserved')
        ingress(); egress()
        checks.append('input-reload-preserves-ci-output-and-foreign-table')
    with subtest('nft stop is scoped to owned table'):
        machine.succeed('systemctl stop nftables.service')
        machine.fail('nft list table inet mrjam-forgejo-coordinator')
        machine.succeed('nft list chain inet synthetic-foreign preserved')
        ingress()
        machine.succeed('systemctl start nftables.service')
        egress(); ingress()
        checks.append('nft-stop-start-preserves-input-and-foreign-table')
    Path(os.environ['out'],'result.json').write_text(json.dumps({
        'schema_version':1, 'checks':checks, 'production_access':False,
        'runner_table_sha256':'${builtins.hashString "sha256" table.content}',
        'limits':['Invented users and socket servers; no Forgejo or CI job',
                  'No full host generation activation or reboot is asserted']
    },sort_keys=True)+'\n')
  '';
}
