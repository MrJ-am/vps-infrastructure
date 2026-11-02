{ nixpkgs }:
let
  pkgs=import nixpkgs {system="x86_64-linux";};
  adoption=pkgs.callPackage ./package.nix {};
  old="/nix/store/7hmdar637aj6m80vrqma57g82pgqvbc1-mrjam-mail-native-adoption-2";
in pkgs.testers.runNixOSTest {
  name="mrjam-archive-adoption-v3-whitespace-only";
  requiredFeatures.kvm=true;
  globalTimeout=600;
  nodes.machine={config,lib,...}:{
    imports=[../../hosts/mrjam-vps/state-adoption.nix];
    system.stateVersion="26.05";
    system.extraDependencies=[ (builtins.storePath old) adoption ];
    virtualisation.memorySize=1024;virtualisation.cores=2;virtualisation.diskSize=2048;virtualisation.vlans=[];
    networking.useDHCP=false;
    users.groups={mrjam-vision-archive.gid=943;mrjam-vision-cycle.gid=945;mrjam-vision-admission.gid=947;synthetic-legacy.gid=984;};
    users.users={
      mrjam-vision-archive={uid=943;group="mrjam-vision-archive";isSystemUser=true;};
      mrjam-vision-cycle={uid=945;group="mrjam-vision-cycle";isSystemUser=true;};
      mrjam-vision-admission={uid=947;group="mrjam-vision-admission";isSystemUser=true;};
      synthetic-legacy={uid=984;group="synthetic-legacy";isSystemUser=true;};
    };
    environment.etc."mail-v3".source=pkgs.lib.fileset.toSource {
      root=./.;
      fileset=pkgs.lib.fileset.unions [ ./adopt.py ./systemd-fixture.py ./schemas ];
    };
    environment.etc."staging-helper/stage_adoption.py".source=../../deployment/stage_adoption.py;
    systemd.services.mrjam-archive-mail-adopt.serviceConfig.ExecStart=lib.mkForce "${adoption}/bin/mrjam-archive-mail-adopt";
    systemd.services.mrjam-cycle-mail-adopt.serviceConfig.ExecStart=lib.mkForce "${adoption}/bin/mrjam-cycle-mail-adopt";
    systemd.services.mrjam-archive-mail-adopt-v2={
      unitConfig.AssertPathIsDirectory="/run/mrjam-archive-mail-adoption";
      serviceConfig=config.systemd.services.mrjam-archive-mail-adopt.serviceConfig // {
        ExecStart=lib.mkForce "${old}/bin/mrjam-archive-mail-adopt";
      };
    };
  };
  testScript=''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    cmd="${pkgs.python3}/bin/python3 -B /etc/mail-v3/systemd-fixture.py "
    checks=[]
    machine.succeed(cmd+"prepare whitespace")
    with subtest("old exact-DDL refusal reproduced in real readonly unit"):
        machine.fail("systemctl start mrjam-archive-mail-adopt-v2.service")
        assert machine.succeed("systemctl show mrjam-archive-mail-adopt-v2.service -p ExecMainStatus --value").strip()=="1"
        machine.fail("test -e /var/lib/mrjam-vision-archive/courriels.sqlite")
        checks.append("v2-whitespace-refusal-without-publication")
    with subtest("new package accepts whitespace and preserves all invented bytes"):
        machine.succeed("systemctl start mrjam-archive-mail-adopt.service mrjam-cycle-mail-adopt.service")
        machine.succeed(cmd+"verify")
        machine.succeed("systemctl start mrjam-archive-mail-adopt.service")
        machine.succeed(cmd+"verify")
        checks.append("v3-real-staging-readonly-publication-preservation-idempotence")
    with subtest("exact old DDL remains equivalent to whitespace DDL"):
        machine.succeed(cmd+"prepare exact")
        machine.succeed("systemctl start mrjam-archive-mail-adopt.service")
        machine.succeed(cmd+"verify")
        checks.append("exact-and-whitespace-same-target-inode-and-bytes")
    for case in ("constraint","default","collision"):
        with subtest(case+" remains a real unit refusal"):
            machine.succeed(cmd+"prepare "+case)
            machine.fail("systemctl start mrjam-archive-mail-adopt.service")
            machine.succeed(cmd+"verify")
            machine.succeed("systemctl reset-failed mrjam-archive-mail-adopt.service")
            checks.append(case+"-refused-without-target-or-source-change")
    machine.succeed("systemctl stop mrjam-archive-mail-adopt.service mrjam-cycle-mail-adopt.service mrjam-archive-mail-adopt-v2.service")
    Path(os.environ["out"],"result.json").write_text(json.dumps({
      "schema_version":1,"passed":True,"checks":checks,"production_access":False,
      "package":"${adoption}","adopter_sha256":"${builtins.hashFile "sha256" ./adopt.py}",
      "fixture_sha256":"${builtins.hashFile "sha256" ./systemd-fixture.py}",
      "test_sha256":"${builtins.hashFile "sha256" ./systemd-test.nix}",
      "original_unit_module_sha256":"${builtins.hashFile "sha256" ../../hosts/mrjam-vps/state-adoption.nix}",
      "staging_sha256":"${builtins.hashFile "sha256" ../../deployment/stage_adoption.py}",
      "limits":["Invented private mail and markers only; no real production content",
                "Production adoption unit policy reused with only ExecStart bound to new package",
                "No SMTP, PostgreSQL or application worker semantics requalified here"]},sort_keys=True)+"\n")
  '';
}
