{ nixpkgs, diagnostic ? false }:
let
  pkgs=import nixpkgs {system="x86_64-linux";};
  tls=pkgs.runCommand "mrjam-provision-invented-tls" {nativeBuildInputs=[pkgs.openssl];} ''
    mkdir -p "$out"
    openssl req -x509 -newkey rsa:2048 -noenc -days 3650 -subj /CN=INVENTED-PROVISION-VM \
      -addext basicConstraints=critical,CA:true -keyout ca-key.pem -out "$out/ca.pem" >/dev/null 2>&1
    openssl req -newkey rsa:2048 -noenc -subj /CN=log.mrj.am \
      -keyout "$out/key.pem" -out leaf.csr >/dev/null 2>&1
    printf '%s\n' 'subjectAltName=DNS:log.mrj.am,DNS:localhost' 'basicConstraints=critical,CA:FALSE' \
      'keyUsage=critical,digitalSignature,keyEncipherment' 'extendedKeyUsage=serverAuth' > leaf.ext
    openssl x509 -req -in leaf.csr -CA "$out/ca.pem" -CAkey ca-key.pem -CAcreateserial -days 3650 \
      -extfile leaf.ext -out "$out/leaf.pem" >/dev/null 2>&1
  '';
  package=pkgs.callPackage ./provision.nix {kanidmCaFile=tls+"/ca.pem";};
  source=pkgs.lib.fileset.toSource {root=./.;fileset=pkgs.lib.fileset.unions [
    ./qualify_provision.py ./provision.py ./probe.py ./adapt.py ./provision_systemd_fixture.py
  ];};
in pkgs.testers.runNixOSTest {
  name="mrjam-human-kanidm-provision-private-unit";
  requiredFeatures.kvm=true;
  globalTimeout=600;
  nodes.machine={lib,...}: {
    imports=[./provisioning-unit.nix];
    system.stateVersion="26.05";
    virtualisation.memorySize=1024;
    virtualisation.cores=1;
    virtualisation.vlans=[];
    networking.hosts."127.0.0.1"=["log.mrj.am"];
    services.mrjamKanidmWorkerProvision={enable=true;inherit package;};
    systemd.services.mrjam-kanidm-worker-provision.serviceConfig.ExecStartPre=lib.mkIf diagnostic (
      let observation=pkgs.writeText "invented-credential-metadata.py" ''
        import json,os,stat
        from pathlib import Path
        root=Path('/run/credentials/mrjam-kanidm-worker-provision.service')
        values={}
        for name,path in [('directory',root),('identity',root/'identity-session'),('access',root/'access-session')]:
            m=path.lstat()
            values[name]={'mode':stat.S_IMODE(m.st_mode),'uid':m.st_uid,'gid':m.st_gid,'links':m.st_nlink,'readonly':bool(os.statvfs(path).f_flag&os.ST_RDONLY)}
        print('SYNTHETIC_CREDENTIAL_META '+json.dumps(values,sort_keys=True),flush=True)
      '';
      in "${pkgs.python3}/bin/python3 -I -S ${observation}");
    environment.systemPackages=[pkgs.python3 pkgs.openssl pkgs.socat];
    system.extraDependencies=[ (builtins.storePath "/nix/store/64r3qy45dngms51i718ddna9p08lczd2-kanidm-1.11.2") source tls ];
    systemd.services.synthetic-kanidm-public-tls={
      wantedBy=["multi-user.target"];
      serviceConfig={ExecStart="${pkgs.socat}/bin/socat TCP4-LISTEN:443,bind=127.0.0.1,reuseaddr,fork TCP4:127.0.0.1:8443";};
    };
  };
  testScript=''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    unit="mrjam-kanidm-worker-provision.service"
    machine.fail("systemctl is-active --quiet "+unit)
    machine.fail("test -e /var/lib/mrjam-identite/kanidm-cycle.token")
    code,output=machine.execute("python3 -I ${source}/provision_systemd_fixture.py ${tls} ${package}",timeout=300)
    if code!=0:
        for line in machine.succeed("journalctl -u "+unit+" --no-pager -o cat").splitlines():
            if line.startswith("SYNTHETIC_CREDENTIAL_META "):
                print(line)
        raise RuntimeError(output)
    result=json.loads(output)
    assert result["passed"] is True and len(result["checks"])==7
    result.update({
      "production_access":False,
      "unit_sha256":"${builtins.hashFile "sha256" ./provisioning-unit.nix}",
      "provision_sha256":"${builtins.hashFile "sha256" ./provision.py}",
      "human_sha256":"${builtins.hashFile "sha256" ./human_login.py}",
      "fixture_sha256":"${builtins.hashFile "sha256" ./provision_systemd_fixture.py}",
      "package":"${package}","provider":"/nix/store/64r3qy45dngms51i718ddna9p08lczd2-kanidm-1.11.2",
      "limits":["Invented accounts, credentials and CA only", "Production package changes the reviewed public CA reference", "Password authentication tested; hardware passkey requires the human's device"]
    })
    Path(os.environ["out"],"result.json").write_text(json.dumps(result,sort_keys=True)+"\n")
  '';
}
