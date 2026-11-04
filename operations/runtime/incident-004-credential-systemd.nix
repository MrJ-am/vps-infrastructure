# Incident 004: actual sealed ELF and blue sandbox, invented credentials only.
# No application/database readiness is claimed by this narrow reader proof.
{ nixpkgs ? /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  lib = pkgs.lib;
  artifact = builtins.storePath /nix/store/hf08v9mbbr9hrjzp5j53691zv0b5dvq5-mrjam-reviewed-mrjam-qualified-artifacts-8bf05fb9065a;
  original = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile /nix/store/i6sihwyslybsjf3qxx8k6pqb18n0wcak-mrjam-runtime-blue/runtime.json));
  runtime = pkgs.writeTextDir "runtime.json" (builtins.toJSON (original // {
    required_capabilities = [ "static-assets" ];
    mateval = null; audition = null; log = null;
  }));
  inspect = pkgs.writeText "inspect-synthetic-systemd-credential.py" ''
    import os, stat, struct
    root='/run/credentials/mrjam-rust-blue.service'
    def acl(path, permission):
        entries=[(1,permission,0xffffffff),(2,permission,os.geteuid()),
                 (4,0,0xffffffff),(16,permission,0xffffffff),(32,0,0xffffffff)]
        expected=struct.pack('<I',2)+b"".join(struct.pack('<HHI',*x) for x in entries)
        assert os.getxattr(path,'system.posix_acl_access')==expected
    parent=os.stat(root,follow_symlinks=False)
    assert stat.S_ISDIR(parent.st_mode) and (parent.st_uid,parent.st_gid)==(0,0)
    assert stat.S_IMODE(parent.st_mode)==0o550
    assert os.statvfs(root).f_flag & os.ST_RDONLY
    acl(root,5)
    for name in ('admission-approval','mateval-activation-sha256'):
        path=root+'/'+name
        value=os.stat(path,follow_symlinks=False)
        assert stat.S_ISREG(value.st_mode) and value.st_nlink==1
        assert (value.st_uid,value.st_gid)==(0,0) and stat.S_IMODE(value.st_mode)==0o440
        assert os.statvfs(path).f_flag & os.ST_RDONLY
        acl(path,4)
    assert not os.access('/run/secrets/incident-approval',os.R_OK)
    print('SYNTHETIC_CREDENTIAL_ACL_VERIFIED')
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-incident-004-actual-credential-reader";
  requiredFeatures.kvm = true;
  globalTimeout = 600;
  nodes.machine = { lib, ... }: {
    imports = [ ../nixos/mrjam-rust.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1024;
    virtualisation.cores = 2;
    virtualisation.vlans = [];
    services.mrjamRust = {
      enable = true;
      slots.blue = {
        enable = true;
        artifactStorePath = builtins.unsafeDiscardStringContext artifact;
        runtimeConfigStorePath = builtins.unsafeDiscardStringContext runtime;
        credentials.admission-approval = "/run/secrets/incident-approval";
        credentials.mateval-activation-sha256 = "/run/secrets/incident-activation";
      };
    };
    users.users.mrjam-rust-blue.uid = 941;
    users.groups.mrjam-rust-blue.gid = 941;
    users.groups.mrjam-log-readers.gid = 940;
    systemd.tmpfiles.rules = [ "d /run/mrjam-identity 0750 root mrjam-log-readers -" ];
    systemd.services.mrjam-rust-blue.serviceConfig = {
      # Diagnostic-only changes: retain sandbox/ELF; avoid restart loops.
      Restart = lib.mkForce "no";
      StandardOutput = lib.mkForce "journal";
      StandardError = lib.mkForce "journal";
      ExecStartPre = "${pkgs.python3}/bin/python3 -I -S ${inspect}";
      SupplementaryGroups = [ "mrjam-log-readers" ];
      BindReadOnlyPaths = [ "/run/mrjam-identity" ];
    };
    system.extraDependencies = [ artifact runtime ] ++ map (asset: builtins.storePath asset.directory) original.assets;
    environment.systemPackages = [ pkgs.curl ];
  };
  testScript = ''
    import json, os
    from pathlib import Path
    start_all()
    machine.wait_for_unit('multi-user.target')
    assert machine.succeed('systemctl --version').splitlines()[0].startswith('systemd 260 (260.2)')
    machine.succeed('install -d -m0700 /run/secrets')
    machine.succeed("printf %s INVENTED_ADMISSION_CREDENTIAL_1234567890 > /run/secrets/incident-approval")
    machine.succeed("printf %s " + 'a'*64 + " > /run/secrets/incident-activation")
    machine.succeed('chmod 0400 /run/secrets/incident-approval /run/secrets/incident-activation')
    checks=[]
    def launch(expected):
        if checks:
            machine.succeed('systemctl reset-failed mrjam-rust-blue.service')
        machine.execute('systemctl start mrjam-rust-blue.service')
        machine.wait_until_succeeds("test $(systemctl show mrjam-rust-blue.service -p ExecMainStatus --value) = 2",timeout=30)
        invocation=machine.succeed('systemctl show mrjam-rust-blue.service -p InvocationID --value').strip()
        messages=machine.succeed('journalctl _SYSTEMD_INVOCATION_ID='+invocation+' -o cat --no-pager')
        assert 'SYNTHETIC_CREDENTIAL_ACL_VERIFIED' in messages
        assert json.loads(messages.splitlines()[-1]) == {'code':expected}
        machine.fail('curl --silent --max-time 1 http://127.0.0.1:38101/readyz')
    with subtest('real credential reader passes before intentionally absent database'):
        launch('DATABASE_UNAVAILABLE')
        checks.append('actual-elf-credential-reader-accepted-systemd-260.2-acl')
    with subtest('invalid synthetic credential remains refused before database'):
        machine.succeed('chmod 0600 /run/secrets/incident-approval')
        machine.succeed('printf %s INVALID > /run/secrets/incident-approval')
        machine.succeed('chmod 0400 /run/secrets/incident-approval')
        launch('INVALID_ADMISSION_APPROVAL_CREDENTIAL')
        checks.append('invalid-credential-refused-without-listener')
    Path(os.environ['out'],'result.json').write_text(json.dumps({
      'schema_version':1,'checks':checks,'systemd':'260.2','artifact':'${artifact}',
      'production_access':False,'application_readiness_qualified':False,
      'limitations':['Invented credential and absent database','Restart and logging differ only for observation','MatEval activation file metadata checked; its application consumer is outside this proof']
    },sort_keys=True)+'\n')
  '';
}
