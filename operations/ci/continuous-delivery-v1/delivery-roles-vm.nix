{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  locked=import ../../forgejo/locked-toolchain.nix {};
  forgejo=locked.forgejo;
  bootstrap=pkgs.callPackage ../../deployment/forgejo-bootstrap/package.nix {forgejoUid=982;forgejoGid=982;};
in pkgs.testers.runNixOSTest {
  name="mrjam-delivery-separated-forgejo-roles";
  globalTimeout=900;
  nodes.machine={config,lib,pkgs,...}:{
    imports=[../../nixos/mrjam-forgejo-host.nix ../../deployment/forgejo-bootstrap/module.nix];
    system.stateVersion="26.05";
    virtualisation.memorySize=1536;virtualisation.cores=2;virtualisation.diskSize=4096;
    virtualisation.qemu.networkingOptions=lib.mkForce [];virtualisation.vlans=[];
    networking.useDHCP=lib.mkForce false;networking.dhcpcd.enable=false;
    services.mrjamForgejoHost={enable=true;uid=982;gid=982;artifactStorePath=builtins.unsafeDiscardStringContext "${forgejo}";};
    services.postgresql={enable=true;package=pkgs.postgresql_17;ensureDatabases=["forgejo"];
      ensureUsers=[{name="forgejo";ensureDBOwnership=true;}];};
    environment.systemPackages=[bootstrap forgejo pkgs.postgresql_17 pkgs.git pkgs.python3 pkgs.curl pkgs.util-linux];
    environment.variables.SYNTHETIC_BOOTSTRAP_PACKAGE="${bootstrap}";
    environment.variables.SYNTHETIC_FORGEJO_PACKAGE="${forgejo}";
    environment.etc."synthetic-forgejo.ini".source=(pkgs.formats.ini {}).generate "synthetic-forgejo.ini"
      (lib.recursiveUpdate config.services.mrjamForgejoHost.settings {
        security={SECRET_KEY="SYNTHETIC-SECRET-KEY-NOT-PRODUCTION";INTERNAL_TOKEN="SYNTHETIC-INTERNAL-TOKEN-NOT-PRODUCTION";};
        oauth2.JWT_SECRET="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
      });
    environment.etc."forgejo-adopt-runtime-role.sql".source=../../forgejo/adopt-runtime-role.sql;
    environment.etc."synthetic-forgejo-policy/reconcile.py".source=../../forgejo/reconcile.py;
    environment.etc."forgejo-bootstrap-fixture.py".source=../../deployment/forgejo-bootstrap/fixture.py;
    environment.etc."delivery-roles/delivery_roles.py".source=./delivery_roles.py;
    environment.etc."delivery-roles/source_snapshot.py".source=./source_snapshot.py;
    environment.etc."delivery-roles/fixture.py".source=./delivery-roles-fixture.py;
  };
  testScript=''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql-setup.service")
    machine.succeed("python3 -B /etc/forgejo-bootstrap-fixture.py prepare")
    machine.succeed("systemctl start forgejo.service")
    machine.wait_for_open_port(3004)
    machine.succeed("systemctl start mrjam-forgejo-bootstrap.service")
    machine.succeed("python3 -B /etc/forgejo-bootstrap-fixture.py seed")
    machine.succeed("python3 -B /etc/delivery-roles/fixture.py")
    proof=json.loads(machine.succeed("cat /var/lib/synthetic-forgejo-proof/delivery-roles.json"))
    machine.succeed("systemctl stop forgejo.service")
    Path(os.environ["out"],"delivery-roles.json").write_text(json.dumps(proof,sort_keys=True)+"\n")
  '';
}
