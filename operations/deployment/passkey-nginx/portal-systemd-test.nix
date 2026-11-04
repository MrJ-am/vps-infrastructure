{ nixpkgs }:
let
  pkgs=import nixpkgs {system="x86_64-linux";};
  runtime=pkgs.python3.withPackages (p:[p.cryptography p.fido2]);
  tls=pkgs.runCommand "invented-passkey-nginx-provider-tls" {nativeBuildInputs=[pkgs.openssl];} ''
    mkdir "$out"
    openssl req -x509 -newkey rsa:2048 -noenc -days 3650 -subj /CN=INVENTED-PASSKEY-VM \
      -addext basicConstraints=critical,CA:true -keyout ca-key.pem -out "$out/ca.pem" >/dev/null 2>&1
    openssl req -newkey rsa:2048 -noenc -subj /CN=log.mrj.am -keyout "$out/key.pem" -out leaf.csr >/dev/null 2>&1
    printf '%s\n' 'subjectAltName=DNS:log.mrj.am,DNS:localhost' 'basicConstraints=critical,CA:FALSE' \
      'keyUsage=critical,digitalSignature,keyEncipherment' 'extendedKeyUsage=serverAuth' > leaf.ext
    openssl x509 -req -in leaf.csr -CA "$out/ca.pem" -CAkey ca-key.pem -CAcreateserial -days 3650 \
      -extfile leaf.ext -out "$out/leaf.pem" >/dev/null 2>&1
  '';
  portal=pkgs.callPackage ../passkey-portal/package.nix {kanidmCaFile=tls+"/ca.pem";};
  provision=pkgs.callPackage ../credentials/provision.nix {kanidmCaFile=tls+"/ca.pem";};
  resultProbe=pkgs.callPackage ../passkey-portal/result-probe.nix {provisionPackage=provision;};
  source=pkgs.lib.fileset.toSource {root=../.;fileset=pkgs.lib.fileset.unions [
    ../credentials/provision.py ../credentials/probe.py ../credentials/adapt.py ../credentials/qualify_provision.py
    ../passkey-portal/portal.py ../passkey-portal/qualify.py ../passkey-portal/result_probe.py
  ];};
  entry=pkgs.writeScriptBin "mrjam-passkey-nginx-route" ''
    #!${pkgs.python3}/bin/python3 -I
    import runpy
    runpy.run_path("/run/synthetic-nginx-helper/route.py",run_name="__main__")
  '';
in pkgs.testers.runNixOSTest {
  name="mrjam-passkey-nginx-real-provider-private-unit";
  requiredFeatures.kvm=true;
  globalTimeout=600;
  nodes.machine={lib,...}: {
    imports=[./unit.nix ../passkey-portal/unit.nix ../credentials/provisioning-unit.nix];
    system.stateVersion="26.05";
    virtualisation.memorySize=2048;
    virtualisation.cores=1;
    virtualisation.vlans=[];
    environment.systemPackages=[runtime pkgs.openssl];
    system.extraDependencies=[portal provision resultProbe source tls (builtins.storePath "/nix/store/64r3qy45dngms51i718ddna9p08lczd2-kanidm-1.11.2")];
    environment.etc."synthetic-nginx/route.py".source=./route.py;
    environment.etc."synthetic-nginx/preflight_passkey_nginx.py".source=../preflight_passkey_nginx.py;
    environment.etc."synthetic-nginx/fixture.py".source=./fixture.py;
    environment.etc."synthetic-nginx/portal-fixture.py".source=./portal_fixture.py;
    environment.etc."synthetic-nginx/start_passkey_portal.py".source=../start_passkey_portal.py;
    environment.etc."synthetic-nginx/production-source-hashes.json".text=builtins.toJSON {
      portal=builtins.listToAttrs (map (name:{inherit name;value=builtins.hashFile "sha256" ("/nix/store/q7ni6r8bb952mcv08fj919vcdjcvznnq-mrjam-kanidm-passkey-portal-1/libexec/"+name);}) ["portal.py" "index.html" "portal.js" "style.css"]);
      result_probe=builtins.hashFile "sha256" /nix/store/8inkp30yx0zc86j99bx0pyzazxm45mxn-mrjam-kanidm-worker-result-probe-1/libexec/result_probe.py;
    };
    services.mrjamPasskeyNginxRoute={enable=true;package=entry;};
    services.mrjamKanidmPasskeyPortal={enable=true;package=portal;};
    services.mrjamKanidmWorkerProvision={enable=true;package=provision;};
    # Exercise the production timeout/ExecStopPost mechanisms without waiting
    # fifteen minutes. No helper or portal function is changed for these tests.
    systemd.services.mrjam-passkey-nginx-route.serviceConfig.RuntimeMaxSec=lib.mkForce 45;
    systemd.services.mrjam-kanidm-passkey-portal.serviceConfig.RuntimeMaxSec=lib.mkForce 48;
    services.nginx={
      enable=true;
      virtualHosts."log.mrj.am"={
        forceSSL=true;
        sslCertificate="${tls}/leaf.pem";
        sslCertificateKey="${tls}/key.pem";
        locations."/"={
          proxyPass="https://127.0.0.1:8443";
          extraConfig=''
            proxy_ssl_verify on;
            proxy_ssl_trusted_certificate ${tls}/ca.pem;
            proxy_ssl_server_name on;
            proxy_ssl_name log.mrj.am;
          '';
        };
      };
    };
  };
  testScript=''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("nginx.service")
    result=json.loads(machine.succeed("${runtime}/bin/python3 -I /etc/synthetic-nginx/portal-fixture.py ${source} ${tls} ${portal} ${provision} ${resultProbe}",timeout=300))
    assert result["passed"] and len(result["checks"])==14
    machine.succeed("systemctl stop nginx")
    result.update({"schema_version":1,"production_access":False,
      "portal_package":"${portal}","provision_package":"${provision}","result_probe_package":"${resultProbe}",
      "route_sha256":"${builtins.hashFile "sha256" ./route.py}",
      "route_module_sha256":"${builtins.hashFile "sha256" ./unit.nix}",
      "portal_source_sha256":"${builtins.hashFile "sha256" ../passkey-portal/portal.py}",
      "portal_module_sha256":"${builtins.hashFile "sha256" ../passkey-portal/unit.nix}",
      "provision_module_sha256":"${builtins.hashFile "sha256" ../credentials/provisioning-unit.nix}",
      "probe_source_sha256":"${builtins.hashFile "sha256" ../passkey-portal/result_probe.py}",
      "opener_source_sha256":"${builtins.hashFile "sha256" ../start_passkey_portal.py}",
      "fixture_sha256":"${builtins.hashFile "sha256" ./portal_fixture.py}",
      "test_sha256":"${builtins.hashFile "sha256" ./portal-systemd-test.nix}",
      "limits":["Invented accounts and software P-256 credentials only; no real Proton Pass browser", "Production code sources/modules with invented CA and route binding", "Enrollment/signing fixture helpers reused; HTTP and systemd observations independent", "Route and portal RuntimeMaxSec shortened to 45/48; opener only PREVIOUS/BINDING replaced"]})
    Path(os.environ["out"],"result.json").write_text(json.dumps(result,sort_keys=True)+"\n")
  '';
}
