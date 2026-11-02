{ nixpkgs }:
let
  pkgs=import nixpkgs {system="x86_64-linux";};
  runtime=pkgs.python3.withPackages (p:[p.cryptography p.fido2]);
  tls=pkgs.runCommand "invented-local-bootstrap-tls" {nativeBuildInputs=[pkgs.openssl];} ''
    mkdir "$out"
    openssl req -x509 -newkey rsa:2048 -noenc -days 3650 -subj /CN=INVENTED-LOCAL-BOOTSTRAP \
      -addext basicConstraints=critical,CA:true -keyout ca-key.pem -out "$out/ca.pem" >/dev/null 2>&1
    openssl req -newkey rsa:2048 -noenc -subj /CN=log.mrj.am -keyout "$out/key.pem" -out leaf.csr >/dev/null 2>&1
    printf '%s\n' 'subjectAltName=DNS:log.mrj.am,DNS:localhost' 'basicConstraints=critical,CA:FALSE' \
      'keyUsage=critical,digitalSignature,keyEncipherment' 'extendedKeyUsage=serverAuth' > leaf.ext
    openssl x509 -req -in leaf.csr -CA "$out/ca.pem" -CAkey ca-key.pem -CAcreateserial -days 3650 \
      -extfile leaf.ext -out "$out/leaf.pem" >/dev/null 2>&1
  '';
  provision=pkgs.callPackage ../credentials-v3/provision.nix {kanidmCaFile=tls+"/ca.pem";};
  source=pkgs.lib.fileset.toSource {root=../.;fileset=pkgs.lib.fileset.unions [
    ./bootstrap.py ./builtin_probe.py ./qualify.py ./vm_fixture.py
    ../passkey-nginx/capability_matrix_fixture.py ../passkey-portal/portal.py ../passkey-portal/qualify.py ../passkey-portal/result_probe.py
    ../credentials/provision.py ../credentials/probe.py ../credentials/adapt.py ../credentials/qualify_provision.py
  ];};
in pkgs.testers.runNixOSTest {
  name="mrjam-kanidm-local-bootstrap-fixed-main";
  requiredFeatures.kvm=true;
  globalTimeout=300;
  nodes.machine={...}:{
    system.stateVersion="26.05";
    virtualisation.memorySize=1024;
    virtualisation.cores=1;
    virtualisation.vlans=[];
    environment.systemPackages=[runtime pkgs.openssl];
    system.extraDependencies=[source tls provision (builtins.storePath "/nix/store/64r3qy45dngms51i718ddna9p08lczd2-kanidm-1.11.2")];
  };
  testScript=''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    result=json.loads(machine.succeed("${runtime}/bin/python3 -I ${source}/kanidm-local-bootstrap/vm_fixture.py ${source} ${tls} ${provision}",timeout=180))
    assert result["passed"] and len(result["checks"])==8
    result.update({"schema_version":1,"production_access":False,"provision_package":"${provision}",
      "bootstrap_source_sha256":"${builtins.hashFile "sha256" ./bootstrap.py}",
      "probe_source_sha256":"${builtins.hashFile "sha256" ./builtin_probe.py}",
      "fixture_source_sha256":"${builtins.hashFile "sha256" ./vm_fixture.py}",
      "test_source_sha256":"${builtins.hashFile "sha256" ./systemd-test.nix}"})
    Path(os.environ["out"],"result.json").write_text(json.dumps(result,sort_keys=True)+"\n")
  '';
}
