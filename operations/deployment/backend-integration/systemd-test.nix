{ nixpkgs }:
let
  pkgs = import nixpkgs {system="x86_64-linux";};
  lib = pkgs.lib;
  guard = import ../boot-guard-package.nix {inherit pkgs;};
  domains = [ "audition.mrj.am" "cloud.mrj.am" "forge.mrj.am" "log.mrj.am" "logique.echos.systems" "principiipetit.io" "vision.mrj.am" "www.principiipetit.io" ];
  ca = pkgs.runCommand "invented-integrated-control-tls" {nativeBuildInputs=[pkgs.openssl];} ''
    mkdir -p "$out"
    openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj /CN=log.mrj.am \
      -addext 'subjectAltName=${lib.concatMapStringsSep "," (host:"DNS:"+host) domains}' \
      -keyout "$out/key.pem" -out "$out/ca.pem" >/dev/null 2>&1
  '';
  helpers = pkgs.runCommand "invented-integrated-application-contracts" {} ''
    mkdir -p "$out/bin" "$out/libexec"
    for name in probe-standalone.py preflight_obligations.py forgejo_sso_probe.py; do
      cp ${./helpers.py} "$out/libexec/$name"
    done
    for name in mrjam-forgejo-probe mrjam-forgejo-cleanup mrjam-first-release-sources-probe mrjam-first-release-governance; do
      printf '#!%s\n' '${pkgs.python3}/bin/python3' > "$out/bin/$name"
      cat ${./helpers.py} >> "$out/bin/$name"
      chmod 0555 "$out/bin/$name"
    done
  '';
  fixture = pkgs.writeText "invented-integrated-control-fixture.py" (builtins.readFile ./fixture.py);
  toolConfig = {
    tools = {
      systemctl="${pkgs.systemd}/bin/systemctl"; nft="${pkgs.nftables}/bin/nft";
      nix="${pkgs.nix}/bin/nix"; nix_store="${pkgs.nix}/bin/nix-store"; nix_env="${pkgs.nix}/bin/nix-env";
      python="${pkgs.python3}/bin/python3"; curl="${pkgs.curl}/bin/curl"; tar="${pkgs.gnutar}/bin/tar";
    };
    helpers = {
      capabilities="${helpers}/libexec/probe-standalone.py";
      obligations="${helpers}/libexec/preflight_obligations.py";
      forgejo_sso="${helpers}/libexec/forgejo_sso_probe.py";
      forgejo_probe="${helpers}/bin/mrjam-forgejo-probe";
      forgejo_cleanup="${helpers}/bin/mrjam-forgejo-cleanup";
      forgejo_sources="${helpers}/bin/mrjam-first-release-sources-probe";
      forgejo_governance="${helpers}/bin/mrjam-first-release-governance";
    };
    ca_file="${ca}/ca.pem"; tls_key="${ca}/key.pem";
    generator="${guard}/bin/mrjam-first-cutover-guard";
    runuser="${pkgs.util-linux}/bin/runuser"; psql="${pkgs.postgresql_17}/bin/psql";
    postgres="${pkgs.postgresql_17}/bin/postgres"; ip="${pkgs.iproute2}/bin/ip";
  };
  privateNames = [ "kanidm" "mrjam-identity" "mrjam-identity-aliases" "mrjam-identity-deletion"
    "vision-embeddings" "redis-nextcloud" "nextcloud-setup" "phpfpm-nextcloud" "forgejo"
    "mrjam-vision-admission" "mrjam-vision-closure" "mrjam-rust-blue" ];
  fileNames = [ "mrjam-worker-credentials-adapt" "mrjam-admission-native-adopt" "mrjam-cycle-mail-adopt" "mrjam-archive-mail-adopt" ];
  sqlNames = [ "mrjam-adopt-matheval" "mrjam-bootstrap-journal" "mrjam-upgrade-forgejo-schema" "mrjam-adopt-forgejo-role" ];
  timerNames = [ "mrjam-identity-aliases" "mrjam-vision-cycle" "mrjam-vision-archive" "mrjam-vision-replay"
    "nextcloud-cron" "mrjam-sauvegarde" "forgejo-backup" "nextcloud-backup"
    "postgresqlBackup-matheval" "postgresqlBackup-nextcloud" ] ++ map (host:"mrjam-acme-renew-"+host) domains;
  identity = name: uid: gid: {isSystemUser=true;inherit uid;group=name;};
in pkgs.testers.runNixOSTest {
  name="mrjam-integrated-cutover-recovery-control";
  requiredFeatures.kvm=true;
  globalTimeout=2400;
  nodes.machine={lib,...}: {
    system.stateVersion="26.05";
    networking.hostName="integrated-synthetic";
    networking.firewall.enable=false;
    virtualisation.memorySize=1536;
    virtualisation.cores=2;
    virtualisation.diskSize=8192;
    virtualisation.vlans=[];
    virtualisation.useBootLoader=true;
    boot.loader.grub.enable=true;
    boot.loader.grub.device="/dev/vda";
    boot.loader.timeout=1;
    boot.growPartition=true;
    fileSystems."/".autoResize=true;
    environment.systemPackages=[pkgs.python3 pkgs.nix pkgs.nftables pkgs.curl pkgs.iproute2];
    system.extraDependencies=[fixture helpers guard ca pkgs.e2fsprogs];
    environment.etc = {
      "integrated-marker".text="INVENTED_INTEGRATION_VM_ONLY\n";
      "synthetic-generation".text="previous";
      "integrated-tools.json".text=builtins.toJSON toolConfig;
    } // builtins.listToAttrs (map (name: { name="integrated-control/"+name; value.source=../. + ("/"+name); })
      [ "release_backend.py" "release_entrypoint.py" "cutover.py" "recovery.py" "generation.py" "snapshot.py"
        "system_control.py" "stage_credentials.py" "stage_adoption.py" ]);
    users.groups={forgejo.gid=982;kanidm.gid=983;nextcloud.gid=990;nginx.gid=60;acme.gid=995;mrjam-metier.gid=984;};
    users.users={forgejo=identity "forgejo" 982 982;kanidm=identity "kanidm" 983 983;
      nextcloud=identity "nextcloud" 990 990;nginx=identity "nginx" 60 60;
      acme=identity "acme" 996 995;mrjam-metier=identity "mrjam-metier" 984 984;};
    services.postgresql={
      enable=true;package=pkgs.postgresql_17;dataDir="/var/lib/postgresql/17";
      enableTCPIP=false;settings.listen_addresses=lib.mkForce "";
      ensureDatabases=["integration_fixture"];
      authentication=''
        local all postgres peer
        local all all reject
        host all all 0.0.0.0/0 reject
        host all all ::/0 reject
      '';
    };
    systemd.services = lib.genAttrs privateNames (_:{serviceConfig={Type="simple";ExecStart="${pkgs.coreutils}/bin/sleep infinity";};})
      // lib.genAttrs (fileNames++sqlNames++["mrjam-forgejo-bootstrap"]++builtins.filter (name: !(builtins.elem name privateNames)) timerNames)
        (_:{serviceConfig={Type="oneshot";ExecStart="${pkgs.coreutils}/bin/true";};})
      // {
        mrjam-adopt-matheval.serviceConfig={Type="oneshot";ExecStart="${pkgs.python3}/bin/python3 ${fixture} adopt";};
        nginx={wantedBy=["multi-user.target"];serviceConfig={Type="simple";ExecStart="${pkgs.python3}/bin/python3 ${fixture} http";};};
        vision-cycle={wantedBy=["multi-user.target"];serviceConfig={Type="simple";ExecStart="${pkgs.python3}/bin/python3 ${fixture} worker";};};
      };
    systemd.timers = lib.genAttrs timerNames (name:{timerConfig={OnActiveSec="1h";Unit=name+".service";};});
    specialisation.staged.configuration={
      imports=[../boot-guard.nix];
      environment.etc."synthetic-generation".text=lib.mkForce "staged";
      systemd.services.nginx.wantedBy=lib.mkForce [];
      systemd.services.vision-cycle.wantedBy=lib.mkForce [];
    };
    specialisation.promoted.configuration={
      imports=[../boot-guard.nix];
      environment.etc."synthetic-generation".text=lib.mkForce "promoted";
    };
  };
  testScript=''
    import json,os
    from pathlib import Path
    machine.start(allow_reboot=True)
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("postgresql-setup.service")
    machine.wait_for_unit("growpart.service")
    machine.succeed("${pkgs.e2fsprogs}/bin/resize2fs /dev/vda1")
    machine.wait_for_unit("nginx.service")
    machine.wait_until_succeeds("${pkgs.curl}/bin/curl --silent --insecure --noproxy '*' https://127.0.0.1/ >/dev/null")
    cmd="${pkgs.python3}/bin/python3 ${fixture} "
    checks=[]
    machine.succeed(cmd+"initialize",timeout=180)
    with subtest("interrupted metadata before PREPARED reobserves untouched host"):
        machine.succeed(cmd+"baseline interrupt-prepared",timeout=240)
        code,closed_output=machine.execute(cmd+"execute interrupt-prepared",timeout=600)
        assert code==70,closed_output
        machine.succeed(cmd+"retry",timeout=600)
        checks.append("initial-before-prepared-full-preflight-retry-without-effects")
    with subtest("real private failure restores paired state and delays old worker"):
        machine.succeed(cmd+"baseline private-failure",timeout=240)
        print(machine.succeed(cmd+"execute private-failure",timeout=600))
        machine.succeed(cmd+"verify private-failure",timeout=120)
        checks.append("private-failure-real-paired-return-and-periodic-writer-after-returned")
    for case in ("interrupt-return-before-snapshot","interrupt-after-adoption"):
        with subtest(case):
            machine.succeed(cmd+"baseline "+case,timeout=240)
            code,closed_output=machine.execute(cmd+"execute "+case,timeout=600)
            assert code==70,closed_output
            machine.succeed(cmd+"recover "+case,timeout=600)
            machine.succeed(cmd+"verify "+case,timeout=120)
            checks.append(case+"-real-recovery")
    with subtest("accepted public writes survive failed public health and HELD"):
        machine.succeed(cmd+"baseline opening-failure",timeout=240)
        machine.succeed(cmd+"execute opening-failure",timeout=600)
        machine.succeed(cmd+"verify opening-failure",timeout=120)
        checks.append("real-public-write-then-held-without-snapshot-or-generation-restore")
    with subtest("real promoted generation timers and nft reopening"):
        machine.succeed(cmd+"baseline success",timeout=240)
        machine.succeed(cmd+"execute success",timeout=600)
        machine.succeed(cmd+"verify success",timeout=120)
        checks.append("real-promoted-live-boot-timers-and-ingress-after-opening")
    Path(os.environ["out"],"result.json").write_text(json.dumps({
      "schema_version":1,"passed":True,"checks":checks,"production_access":False,
      "backend_sha256":"${builtins.hashFile "sha256" ../release_backend.py}",
      "cutover_sha256":"${builtins.hashFile "sha256" ../cutover.py}",
      "recovery_sha256":"${builtins.hashFile "sha256" ../recovery.py}",
      "fixture_sha256":"${builtins.hashFile "sha256" ./fixture.py}",
      "test_sha256":"${builtins.hashFile "sha256" ./systemd-test.nix}",
      "system_control_sha256":"${builtins.hashFile "sha256" ../system_control.py}",
      "snapshot_sha256":"${builtins.hashFile "sha256" ../snapshot.py}",
      "generation_sha256":"${builtins.hashFile "sha256" ../generation.py}",
      "real_postgresql":True,"real_systemd_and_generator":True,"real_nixos_generations":True,"real_nft_namespace_ingress":True,
      "limits":["Invented application services and helper contracts; not full application qualification",
                "HOST and PREVIOUS constants bound to this invented VM; backend functions unchanged",
                "Interruptions injected only at exact durable boundaries; no production entrypoint used in this first fixture",
                "Offline single-user PostgreSQL observation after HELD reads the retained invented logical row"]
    },sort_keys=True)+"\n")
  '';
}
