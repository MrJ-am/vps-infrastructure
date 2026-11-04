{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {} }:
pkgs.testers.runNixOSTest {
  name="mrjam-nginx-reload-initial-transition";
  requiredFeatures.kvm=false;
  globalTimeout=420;
  nodes.machine={ lib, ... }: {
    system.stateVersion="26.05";
    virtualisation.memorySize=768;
    virtualisation.cores=1;
    virtualisation.vlans=[];
    environment.systemPackages=[pkgs.curl];
    services.nginx={
      enable=true;
      enableReload=false;
      defaultHTTPListenPort=18080;
      virtualHosts."synthetic.invalid".locations."/".return="200 'unchanged'";
    };
    systemd.services.nginx={ restartIfChanged=false; stopIfChanged=false; };
    specialisation.reload.configuration.services.nginx.enableReload=lib.mkForce true;
  };
  testScript=''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit('nginx.service')
    machine.wait_until_succeeds("test $(curl -fsS http://127.0.0.1:18080/) = unchanged")
    original=machine.succeed('readlink -f /run/current-system').strip()
    candidate=original+'/specialisation/reload'
    old_master=machine.succeed('systemctl show nginx -p MainPID --value').strip()
    machine.succeed(candidate+'/bin/switch-to-configuration test',timeout=120)
    machine.succeed('${pkgs.nginx}/bin/nginx -t -c /etc/nginx/nginx.conf')
    # The old master was started with an immutable -c path. Exactly this
    # initial transition needs a restart; later activations only reload.
    machine.succeed('systemctl restart nginx.service',timeout=60)
    master=machine.succeed('systemctl show nginx -p MainPID --value').strip()
    assert master!=old_master
    command=machine.succeed('cat /proc/'+master+'/cmdline')
    assert '/etc/nginx/nginx.conf' in command
    machine.wait_until_succeeds("test $(curl -fsS http://127.0.0.1:18080/) = unchanged")
    machine.succeed('systemctl reload nginx.service')
    assert machine.succeed('systemctl show nginx -p MainPID --value').strip()==master
    machine.succeed(original+'/bin/switch-to-configuration test',timeout=120)
    machine.succeed('systemctl restart nginx.service',timeout=60)
    machine.wait_until_succeeds("test $(curl -fsS http://127.0.0.1:18080/) = unchanged")
    returned=machine.succeed('systemctl show nginx -p MainPID --value').strip()
    assert '/etc/nginx/nginx.conf' not in machine.succeed('cat /proc/'+returned+'/cmdline')
    Path(os.environ['out'],'result.json').write_text(json.dumps({
      'schema_version':1,'transition_and_return_passed':True,
      'initial_restart_required':True,'subsequent_reload_preserves_master':True,
      'production_activation':False,'continuous_service_during_initial_restart_claimed':False
    },indent=2)+'\n')
  '';
}
