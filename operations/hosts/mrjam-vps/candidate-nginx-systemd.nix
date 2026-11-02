# Execute the exact built candidate gateway with invented TLS material only.
{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  domains = [ "audition.mrj.am" "cloud.mrj.am" "forge.mrj.am" "log.mrj.am"
    "logique.echos.systems" "principiipetit.io" "vision.mrj.am" "www.principiipetit.io" ];
  gateway = builtins.storePath "/nix/store/9mhmiqk0cfy419vfkxaxhdhnf6pjd734-nginx.conf";
  nginx = builtins.storePath "/nix/store/hrsgwp6dqnr9y9svhjzvxw0phgmqvnqk-nginx-1.30.4";
  tls = pkgs.runCommand "mrjam-candidate-gateway-invented-tls" { nativeBuildInputs = [ pkgs.openssl ]; } ''
    mkdir "$out"
    openssl req -x509 -newkey rsa:2048 -noenc -days 3650 -subj /CN=INVENTED-CANDIDATE-GATEWAY \
      -addext 'subjectAltName=${pkgs.lib.concatMapStringsSep "," (name: "DNS:${name}") domains}' \
      -keyout "$out/key.pem" -out "$out/certificate.pem" >/dev/null 2>&1
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-built-candidate-nginx-boundaries";
  requiredFeatures.kvm = true;
  globalTimeout = 300;
  nodes.machine = { ... }: {
    system.stateVersion = "26.05";
    virtualisation.memorySize = 768;
    virtualisation.cores = 1;
    virtualisation.vlans = [ ];
    users.groups.nginx.gid = 60;
    users.users.nginx = { isSystemUser = true; uid = 60; group = "nginx"; };
    environment.systemPackages = [ pkgs.curl pkgs.openssl ];
    system.extraDependencies = [ gateway nginx tls ];
    systemd.services.synthetic-candidate-nginx = {
      preStart = ''
        install -d -m0755 /var/lib/acme/acme-challenge/.well-known/acme-challenge /run/nginx /var/cache/nginx /var/log/nginx
        printf '%s' 'INVENTED-HTTP-01-TOKEN' > /var/lib/acme/acme-challenge/.well-known/acme-challenge/qualification
        ${pkgs.lib.concatMapStringsSep "\n" (domain: ''
          install -d -m0755 /var/lib/acme/${domain}
          install -m0644 ${tls}/certificate.pem /var/lib/acme/${domain}/fullchain.pem
          install -m0600 ${tls}/key.pem /var/lib/acme/${domain}/key.pem
        '') domains}
        ${nginx}/bin/nginx -t -c ${gateway}
      '';
      serviceConfig = {
        Type = "simple";
        ExecStart = "${nginx}/bin/nginx -c ${gateway}";
        KillSignal = "SIGQUIT";
      };
    };
  };
  testScript = ''
    import json,os,shlex
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    machine.succeed("systemctl start synthetic-candidate-nginx")
    machine.wait_for_open_port(443)
    domains=json.loads('${builtins.toJSON domains}')
    checks=[]
    def status(host,path,extra=""):
        return machine.succeed("curl --silent --show-error --noproxy '*' --cacert ${tls}/certificate.pem --resolve "+host+":443:127.0.0.1 --output /dev/null --write-out '%{http_code}' "+extra+" "+shlex.quote("https://"+host+path)).strip()
    with subtest("all eight TLS hosts accept only the declared certificates"):
        for host in domains:
            code=status(host,"/")
            assert code in ("200","301","302","308","502"), "unexpected configured host refusal"
        machine.fail("curl --silent --show-error --noproxy '*' --insecure --resolve unknown.invalid:443:127.0.0.1 https://unknown.invalid/")
        checks.append("exact-eight-tls-vhosts-and-unknown-host-refusal")
    with subtest("renewal challenges remain reachable through existing HTTP redirects"):
        for host in domains:
            response=machine.succeed("curl --silent --show-error --fail --location --noproxy '*' --cacert ${tls}/certificate.pem --resolve "+host+":80:127.0.0.1 --resolve "+host+":443:127.0.0.1 "+shlex.quote("http://"+host+"/.well-known/acme-challenge/qualification"))
            assert response=="INVENTED-HTTP-01-TOKEN"
        checks.append("eight-retained-http01-challenge-routes")
    with subtest("application diagnostics and native administrative paths remain private"):
        for host in ("audition.mrj.am","vision.mrj.am","principiipetit.io","logique.echos.systems"):
            for path in ("/readyz","/healthz"):
                assert status(host,path)=="404"
        for path in ("/v1/raw/invented","/v1/oauth2/invented","/v1/service_account/invented","/scim/invented"):
            assert status("log.mrj.am",path)=="404"
        assert status("log.mrj.am","/realms/invented")=="410"
        checks.append("private-diagnostics-and-native-administration")
    with subtest("canonical MatEval mount and www redirect are exact"):
        for host,path,target in (("principiipetit.io","/","/matheval/"),("www.principiipetit.io","/matheval/a?b=c","https://principiipetit.io/matheval/a?b=c")):
            result=machine.succeed("curl --silent --show-error --noproxy '*' --cacert ${tls}/certificate.pem --resolve "+host+":443:127.0.0.1 --output /dev/null --write-out '%{http_code} %{redirect_url}' "+shlex.quote("https://"+host+path)).strip()
            expected=target if target.startswith("https:") else "https://"+host+target
            assert result=="308 "+expected
        checks.append("matheval-prefix-and-canonical-www")
    with subtest("Nextcloud local password endpoints are blocked before PHP"):
        for path in ("/login","/index.php/login","/lostpassword/email","/index.php/lostpassword/email"):
            assert status("cloud.mrj.am",path,"--request POST --data "+shlex.quote(""))=="403"
        checks.append("nextcloud-local-password-posts-refused")
    machine.succeed("systemctl stop synthetic-candidate-nginx")
    Path(os.environ["out"],"result.json").write_text(json.dumps({
      "schema_version":1,"checks":checks,"production_access":False,
      "nginx_configuration":"${gateway}","nginx_configuration_sha256":"${builtins.hashFile "sha256" gateway}",
      "nginx":"${nginx}","fixture_sha256":"${builtins.hashFile "sha256" ./candidate-nginx-systemd.nix}",
      "limits":["Invented TLS material and isolated VM only", "Upstream application services deliberately absent; no readiness or human SSO claim"]
    },sort_keys=True)+"\n")
  '';
}
