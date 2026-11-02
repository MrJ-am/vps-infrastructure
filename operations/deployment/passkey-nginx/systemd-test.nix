{ nixpkgs, diagnostic ? false }:
let
  pkgs=import nixpkgs { system="x86_64-linux"; };
  tls=pkgs.runCommand "invented-temporary-route-tls" { nativeBuildInputs=[pkgs.openssl]; } ''
    mkdir "$out"
    openssl req -x509 -newkey rsa:2048 -noenc -days 3650 -subj /CN=INVENTED-ROUTE-TEST \
      -addext 'subjectAltName=DNS:log.mrj.am,DNS:other.invalid' -keyout "$out/key.pem" -out "$out/certificate.pem" >/dev/null 2>&1
  '';
  entry=pkgs.writeScriptBin "mrjam-passkey-nginx-route" ''
    #!${pkgs.python3}/bin/python3 -I
    import runpy
    ${pkgs.lib.optionalString diagnostic ''
    import sys,json,subprocess
    actual_run=subprocess.run
    def diagnostic_run(args,**kwargs):
        diagnostic_nginx=args[0].endswith("/bin/nginx") and "-t" in args
        if diagnostic_nginx:kwargs["stderr"]=subprocess.PIPE
        result=actual_run(args,**kwargs)
        if diagnostic_nginx and result.returncode:
            print("SYNTHETIC_NGINX_TEST "+result.stderr[:4096].decode(errors="replace"),flush=True)
        return result
    subprocess.run=diagnostic_run
    def trace(frame,event,arg):
        if event=="exception" and frame.f_code.co_filename.endswith("/route.py"):
            print("SYNTHETIC_ROUTE_FRAME "+json.dumps({"line":frame.f_lineno,"function":frame.f_code.co_name,"type":arg[0].__name__}),flush=True)
        return trace
    sys.settrace(trace)
    ''}
    runpy.run_path("/run/synthetic-nginx-helper/route.py",run_name="__main__")
  '';
in pkgs.testers.runNixOSTest {
  name="mrjam-temporary-passkey-nginx-restoration";
  requiredFeatures.kvm=true;
  globalTimeout=360;
  nodes.machine={lib,...}: {
    imports=[./unit.nix];
    system.stateVersion="26.05";
    virtualisation.memorySize=768;
    virtualisation.cores=1;
    virtualisation.vlans=[];
    environment.systemPackages=[pkgs.python3 pkgs.curl];
    environment.etc."synthetic-nginx/route.py".source=./route.py;
    environment.etc."synthetic-nginx/preflight_passkey_nginx.py".source=../preflight_passkey_nginx.py;
    environment.etc."synthetic-nginx/fixture.py".source=./fixture.py;
    environment.etc."synthetic-nginx/certificate.pem".source="${tls}/certificate.pem";
    environment.etc."synthetic-nginx/key.pem".source="${tls}/key.pem";
    services.mrjamPasskeyNginxRoute={enable=true;package=entry;};
    # Only shorten the systemd expiration during the local synthetic test.
    systemd.services.mrjam-passkey-nginx-route.serviceConfig.RuntimeMaxSec=lib.mkForce 12;
    services.nginx={
      enable=true;
      preStart=''
        if [ -e /run/synthetic-nginx/refuse-next-start ]; then
          rm /run/synthetic-nginx/refuse-next-start
          exit 1
        fi
        mkdir -p /run/synthetic-nginx
        install -m0600 ${tls}/certificate.pem /run/synthetic-nginx/certificate.pem
        install -m0600 ${tls}/key.pem /run/synthetic-nginx/key.pem
      '';
      virtualHosts={
        "log.mrj.am"={
          forceSSL=true;
          sslCertificate="/run/synthetic-nginx/certificate.pem";
          sslCertificateKey="/run/synthetic-nginx/key.pem";
          locations."/".return="200 'OLD-KANIDM-ROUTE'";
        };
        "other.invalid"={
          forceSSL=true;
          sslCertificate="/run/synthetic-nginx/certificate.pem";
          sslCertificateKey="/run/synthetic-nginx/key.pem";
          locations."/".return="200 'OTHER-UNMODIFIED'";
        };
      };
    };
    # Permit the existing synthetic Nginx pre-start fixture, as its nginx user.
    systemd.tmpfiles.rules=["d /run/synthetic-nginx 0750 nginx nginx -"];
    systemd.services.nginx.serviceConfig.ReadWritePaths=["/run/synthetic-nginx"];
    systemd.services.synthetic-portal-socket.serviceConfig={
      ExecStart="${pkgs.python3}/bin/python3 -I -S /etc/synthetic-nginx/fixture.py socket";
      User="root";Group="root";
    };
  };
  testScript=''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("nginx.service")
    machine.succeed("systemctl start synthetic-portal-socket")
    machine.wait_until_succeeds("test -S /run/mrjam-kanidm-passkey-portal/http.sock")
    result=json.loads(machine.succeed("python3 -I -S /etc/synthetic-nginx/fixture.py qualify",timeout=180))
    assert result["passed"] and len(result["checks"])==9
    machine.succeed("systemctl stop synthetic-portal-socket nginx")
    result.update({"schema_version":1,"production_access":False,
      "route_sha256":"${builtins.hashFile "sha256" ./route.py}",
      "module_sha256":"${builtins.hashFile "sha256" ./unit.nix}",
      "probe_sha256":"${builtins.hashFile "sha256" ../preflight_passkey_nginx.py}",
      "fixture_sha256":"${builtins.hashFile "sha256" ./fixture.py}",
      "test_sha256":"${builtins.hashFile "sha256" ./systemd-test.nix}",
      "limits":["Invented TLS and socket HTTP fixture only; real portal qualified separately", "RuntimeMaxSec shortened from 900 to 12 for expiration case", "Exact helper source; only immutable binding and fixed runtime entry wrapper differ"]})
    Path(os.environ["out"],"result.json").write_text(json.dumps(result,sort_keys=True)+"\n")
  '';
}
