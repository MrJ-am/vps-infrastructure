{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {} }:
let
  backend = pkgs.writeText "synthetic-slot-backends.py" ''
    import json,threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from pathlib import Path
    ledger=set();lock=threading.Lock();release=threading.Event()
    def handler(slot):
      class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
          if self.path=='/release':release.set()
          if self.path=='/slow':
            Path('/tmp/slow-entered').touch();release.wait(120)
          body=str(len(ledger)).encode() if self.path=='/count' else slot.encode()
          self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_POST(self):
          size=int(self.headers.get('Content-Length','0'));assert 0<size<=32
          body=self.rfile.read(size)
          with lock:
            duplicate=body in ledger;ledger.add(body)
          self.send_response(409 if duplicate else 201);self.send_header('Content-Length','0');self.end_headers()
      return Handler
    servers=[ThreadingHTTPServer(('127.0.0.1',port),handler(slot)) for slot,port in [('blue',38101),('green',38102)]]
    for server in servers:threading.Thread(target=server.serve_forever,daemon=True).start()
    threading.Event().wait()
  '';
  load = pkgs.writeText "synthetic-continuous-writes.py" ''
    import http.client,json,time
    from pathlib import Path
    errors=[];count=0;end=time.monotonic()+180
    Path('/tmp/load-ready').touch()
    while time.monotonic()<end and not Path('/tmp/load-stop').exists():
      connection=http.client.HTTPConnection('127.0.0.1',18080,timeout=5)
      try:
        connection.request('POST','/write',str(count).encode());response=connection.getresponse();response.read()
        if response.status!=201:errors.append('HTTP_'+str(response.status))
      except Exception as error:errors.append(type(error).__name__)
      finally:connection.close()
      count+=1;time.sleep(.01)
    Path('/tmp/load-result.json').write_text(json.dumps({'writes':count,'errors':errors}))
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-nixos-graceful-routing";
  requiredFeatures.kvm = false;
  globalTimeout = 480;
  nodes.machine = { lib, ... }: {
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1024;
    virtualisation.cores = 1;
    virtualisation.vlans = [];
    environment.systemPackages = [ pkgs.curl pkgs.python3 ];
    services.nginx = {
      enable = true;
      enableReload = true;
      defaultHTTPListenPort = 18080;
      virtualHosts."synthetic.invalid".locations."/" = {
        proxyPass = "http://127.0.0.1:38101";
        extraConfig = "proxy_buffering off; proxy_read_timeout 180s;";
      };
    };
    systemd.services.nginx = { restartIfChanged = false; stopIfChanged = false; };
    systemd.services.synthetic-backends = {
      wantedBy = [ "multi-user.target" ];
      serviceConfig.ExecStart = "${pkgs.python3}/bin/python3 ${backend}";
    };
    environment.etc."synthetic-load.py".source = load;
    specialisation.green.configuration = {
      services.nginx.virtualHosts."synthetic.invalid".locations."/".proxyPass = lib.mkForce "http://127.0.0.1:38102";
    };
  };
  testScript = ''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit('multi-user.target')
    machine.wait_for_unit('nginx.service')
    machine.wait_for_open_port(38101)
    machine.wait_for_open_port(38102)
    machine.wait_until_succeeds("test $(curl -fsS http://127.0.0.1:18080/) = blue")
    original=machine.succeed('readlink -f /run/current-system').strip()
    master=machine.succeed('systemctl show nginx.service -p MainPID --value').strip()
    backend=machine.succeed('systemctl show synthetic-backends.service -p MainPID --value').strip()
    checks=[]
    machine.succeed('systemd-run --unit synthetic-load python3 /etc/synthetic-load.py')
    machine.wait_until_succeeds('test -f /tmp/load-ready')
    machine.succeed('systemd-run --unit synthetic-long curl -fsS http://127.0.0.1:18080/slow -o /tmp/slow-result')
    machine.wait_until_succeeds('test -f /tmp/slow-entered')
    with subtest('actual NixOS activation reloads the same nginx master'):
      machine.succeed(original+'/specialisation/green/bin/switch-to-configuration test',timeout=120)
      machine.wait_until_succeeds("test $(curl -fsS http://127.0.0.1:18080/) = green")
      assert machine.succeed('systemctl show nginx.service -p MainPID --value').strip()==master
      assert machine.succeed('systemctl show synthetic-backends.service -p MainPID --value').strip()==backend
      machine.fail('test -s /tmp/slow-result')
      machine.succeed('curl -fsS http://127.0.0.1:38101/release > /dev/null')
      machine.wait_until_succeeds('test -s /tmp/slow-result')
      assert machine.succeed('cat /tmp/slow-result')=='blue'
      checks.append('nixos-switch-preserves-master-backends-and-long-old-response')
    with subtest('return generation uses the same graceful reload'):
      machine.succeed(original+'/bin/switch-to-configuration test',timeout=120)
      machine.wait_until_succeeds("test $(curl -fsS http://127.0.0.1:18080/) = blue")
      assert machine.succeed('systemctl show nginx.service -p MainPID --value').strip()==master
      machine.succeed('touch /tmp/load-stop')
      machine.wait_until_succeeds('test -s /tmp/load-result.json')
      result=json.loads(machine.succeed('cat /tmp/load-result.json'))
      assert result['writes']>=20 and result['errors']==[],result
      assert int(machine.succeed('curl -fsS http://127.0.0.1:38101/count'))==result['writes']
      checks.append('generation-return-no-write-errors-loss-or-duplicates')
    Path(os.environ['out'],'result.json').write_text(json.dumps({
      'schema_version':1,'checks':checks,'synthetic_writes':result['writes'],
      'nginx_master_unchanged':True,'production_activation':False,
      'limitations':['Synthetic HTTP fixture in isolated NixOS VM','No Rust session, artifact admission or production cutover claim']
    },indent=2)+'\n')
  '';
}
