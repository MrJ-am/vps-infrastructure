{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {} }:
let
  package=import ./admission-package.nix {};
  proposal=package.bindings.proposal;
  probe=pkgs.writeText "admission-registry-probe.py" ''
    import json,os,sys
    from pathlib import Path
    sys.path.insert(0,'${package}/lib')
    import admission_control as R
    try:
        value=R.load(sys.argv[1])
        if os.environ.get('MRJAM_PRIVATE_ROOT')=='1':
            assert not Path(value['authority']['verifier']).exists()
        print(json.dumps({'uid':os.getuid(),'proposal':value['authority']['accepted_proposals'][0],
                          'steps':len(value['authority']['required_steps'])}))
    except Exception:
        print('ADMISSION_REFUSED');raise SystemExit(1) from None
  '';
  controlClosure=pkgs.closureInfo {rootPaths=[package probe pkgs.python3];};
  controlRoot=pkgs.runCommand "mrjam-admission-client-metadata-root" {} ''
    mkdir -p "$out/nix/store" "$out/var/lib/mrjam-validation-admissions" "$out/dev" "$out/proc" "$out/sys" "$out/run" "$out/etc" "$out/tmp"
    ${pkgs.python3}/bin/python3 - '${controlClosure}/store-paths' <<'PY'
    import pathlib,sys
    paths=pathlib.Path(sys.argv[1]).read_text().splitlines()
    assert not any('mrjam-rust-toolchain' in p or 'cargo-vendor' in p for p in paths)
    PY
    while IFS= read -r path; do cp -a --reflink=auto "$path" "$out/nix/store/"; done < ${controlClosure}/store-paths
  '';
in pkgs.testers.runNixOSTest {
  name="mrjam-admission-registry-real-permissions";
  requiredFeatures.kvm=false;
  globalTimeout=300;
  nodes.machine={ ... }: {
    system.stateVersion="26.05";
    virtualisation.memorySize=768;
    virtualisation.cores=1;
    virtualisation.vlans=[];
    users.users.intake={isSystemUser=true;uid=1101;group="intake";};
    users.groups.intake.gid=1101;
    environment.systemPackages=[pkgs.python3 pkgs.util-linux];
    systemd.tmpfiles.rules=["d /var/lib/mrjam-validation-admissions 0755 root root -"];
    environment.etc."admission-seed.json".source=package.recordFile;
    environment.etc."admission-probe.py".source=probe;
    systemd.services.synthetic-admission-private-client.serviceConfig={
      Type="oneshot"; User="intake"; Group="intake";
      RootDirectory=controlRoot;
      BindReadOnlyPaths=["/var/lib/mrjam-validation-admissions"];
      ExecStart="${pkgs.python3}/bin/python3 -I -S ${probe} ${proposal}";
      Environment="MRJAM_PRIVATE_ROOT=1";
      ProtectSystem="strict"; PrivateNetwork=true; PrivateDevices=true;
      NoNewPrivileges=true; CapabilityBoundingSet="";
      StandardOutput="journal"; StandardError="journal";
    };
  };
  testScript=''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit('multi-user.target')
    machine.succeed("date -s '@${toString (package.policy.not_before+120)}'")
    registry='/var/lib/mrjam-validation-admissions/'
    proposal='${proposal}'
    selected=registry+proposal+'.json'
    run='runuser -u intake -- python3 /etc/admission-probe.py '
    machine.succeed('cp -r ${package.metadataSeed} '+registry+'metadata')
    machine.succeed('install -m 0444 /etc/admission-seed.json '+selected)
    value=json.loads(machine.succeed(run+proposal))
    assert value=={'uid':1101,'proposal':proposal,'steps':74}
    machine.succeed('systemctl start synthetic-admission-private-client.service')
    machine.fail('runuser -u intake -- touch '+registry+'unauthorized')
    machine.fail('runuser -u intake -- chmod 0644 '+selected)
    machine.fail('runuser -u intake -- rm -f '+selected)
    machine.fail(run+'0'*64)
    machine.succeed('chmod 0644 '+selected)
    machine.fail(run+proposal)
    machine.succeed('chmod 0444 '+selected)
    machine.succeed('mv '+selected+' /var/lib/admission-saved.json')
    machine.succeed('ln -s /var/lib/admission-saved.json '+selected)
    machine.fail(run+proposal)
    machine.succeed('rm '+selected)
    machine.succeed('mv /var/lib/admission-saved.json '+selected)
    machine.succeed(run+proposal)
    machine.succeed('rm '+selected)
    machine.fail(run+proposal)
    machine.fail('systemctl start synthetic-admission-private-client.service')
    Path(os.environ['out'],'result.json').write_text(json.dumps({
      'schema_version':1,'root_admission_read_by_uid':1101,
      'unprivileged_create_chmod_delete_refused':True,
      'missing_writable_symlink_revoked_entries_refused':True,
      'private_client_root_excludes_compiler_and_reads_metadata_only':True,
      'production_activation':False,
      'limits':['Registry and configuration selection only; no signing key or compiler invocation in this VM.']
    },indent=2)+'\n')
  '';
}
