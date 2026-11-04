# Actual retained/new Rust executables and packaged interfaces; invented VM.
# SQL, authenticated sessions and production readiness are outside this test.
{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}, bootSwap ? false }:
let
  lib=pkgs.lib;
  old=builtins.storePath /nix/store/wasrcrd9a76d1gpzzrhs0qkxbdqzwdrw-mrjam-server-mateval-typed-readiness-1;
  new=import ./delivery-server-qualification.nix;
  complete=import ./delivery-complete-runtime-qualification.nix;
  original=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (complete+"/runtime.json")));
  runtime=pkgs.writeTextDir "runtime.json" (builtins.toJSON (original // {
    required_capabilities=["static-assets"];
    identity=null;vision=null;mateval=null;audition=null;log=null;
  }));
  routes=port: lib.genAttrs original.public_hosts (host: {
    locations."/"={proxyPass="http://127.0.0.1:${toString port}";extraConfig="proxy_set_header Host ${host};";};
  });
  probe=pkgs.writeText "rust-interface-probe.py" ''
    import hashlib,http.client,json,sys
    result={}
    for host,path in [('audition.mrj.am','/'),('log.mrj.am','/'),('logique.echos.systems','/'),('principiipetit.io','/matheval/'),('vision.mrj.am','/')]:
      c=http.client.HTTPConnection('127.0.0.1',18080,timeout=5)
      c.request('GET',path,headers={'Host':host});r=c.getresponse();raw=r.read(2097153)
      assert r.status==200 and 0<len(raw)<=2097152
      result[host]=hashlib.sha256(raw).hexdigest();c.close()
    print(json.dumps(result,sort_keys=True))
  '';
in pkgs.testers.runNixOSTest {
  name="mrjam-actual-rust-two-slot-routing";
  requiredFeatures.kvm=false;
  qemu.forceAccel=false;
  globalTimeout=900;
  nodes.machine={lib,...}:{
    imports=[../../nixos/mrjam-rust.nix];
    system.stateVersion="26.05";
    virtualisation.memorySize=1536;virtualisation.cores=2;virtualisation.vlans=[];
    services.mrjamRust={enable=true;slots={
      blue={enable=true;artifactStorePath=builtins.unsafeDiscardStringContext (toString old);runtimeConfigStorePath=builtins.unsafeDiscardStringContext (toString runtime);};
      green={enable=true;artifactStorePath=builtins.unsafeDiscardStringContext (toString new);runtimeConfigStorePath=builtins.unsafeDiscardStringContext (toString runtime);};
    };};
    system.extraDependencies=[old new runtime]++map (asset: builtins.storePath asset.directory) original.assets;
    services.nginx={enable=true;enableReload=true;defaultHTTPListenPort=18080;virtualHosts=routes 38101;};
    systemd.services.nginx={restartIfChanged=false;stopIfChanged=false;};
    systemd.services.mrjam-rust-blue.wantedBy=lib.optionals bootSwap ["multi-user.target"];
    environment.systemPackages=[pkgs.curl pkgs.python3];
    specialisation.green.configuration={
      services.nginx.virtualHosts=lib.mkForce (routes 38102);
      systemd.services.mrjam-rust-blue.wantedBy=lib.mkForce [];
      systemd.services.mrjam-rust-green.wantedBy=lib.mkForce (lib.optionals bootSwap ["multi-user.target"]);
    };
  };
  testScript=''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit('multi-user.target')
    machine.wait_for_unit('nginx.service')
    ${if bootSwap then "machine.wait_for_unit('mrjam-rust-blue.service')" else "machine.fail('systemctl is-active --quiet mrjam-rust-blue.service')"}
    machine.fail('systemctl is-active --quiet mrjam-rust-green.service')
    machine.succeed('systemctl start mrjam-rust-blue.service mrjam-rust-green.service')
    for port in (38101,38102):
      machine.wait_until_succeeds('curl -fsS -H "Host: audition.mrj.am" http://127.0.0.1:'+str(port)+'/readyz >/dev/null',timeout=90)
    def pid(unit):return machine.succeed('systemctl show '+unit+' -p MainPID --value').strip()
    units=['nginx.service','mrjam-rust-blue.service','mrjam-rust-green.service']
    pids={u:pid(u) for u in units}
    assert machine.succeed('readlink /proc/'+pids['mrjam-rust-green.service']+'/exe').strip()=='${new}/libexec/mrjam-server'
    probe='${pkgs.python3}/bin/python3 ${probe}'
    initial=json.loads(machine.succeed(probe))
    base=machine.succeed('readlink -f /run/current-system').strip()
    machine.succeed(base+'/specialisation/green/bin/switch-to-configuration test',timeout=180)
    assert {u:pid(u) for u in units}==pids
    assert json.loads(machine.succeed(probe))==initial
    machine.succeed(base+'/bin/switch-to-configuration test',timeout=180)
    assert {u:pid(u) for u in units}==pids
    assert json.loads(machine.succeed(probe))==initial
    machine.succeed('systemctl stop mrjam-rust-green.service',timeout=30)
    assert json.loads(machine.succeed(probe))==initial
    machine.succeed('test "$(systemctl show mrjam-rust-green.service -p Result --value)" = success')
    Path(os.environ['out'],'result.json').write_text(json.dumps({
      'passed':True,'old_server':'${old}','new_server':'${new}',
      'boot_policy_swapped':${if bootSwap then "True" else "False"},
      'checks':['inactive-slot-does-not-autostart','both-real-executables-ready-static-only','wrapped-elf-identity',
                'five-interfaces-identical','graceful-route-change-and-return-same-pids','inactive-sigterm-stop'],
      'production_access':False,'limitations':['static-only runtime','SQL and authenticated sessions not tested here','no long request in this case']},sort_keys=True)+'\n')
  '';
}
