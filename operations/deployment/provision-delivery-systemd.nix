# Local qualification only. Build artifactsOnly first, export the two invented
# roots, gzip/base64 their export and base64 their manifest into bundle JSON.
# Encoded bytes prevent Nix's reference scanner from preinstalling the test roots.
{ nixpkgs, artifactsOnly ? false, bundle ? null }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  package = pkgs.runCommand "mrjam-kanidm-worker-provision-2" { } ''
    mkdir -p "$out/bin"
    cat > "$out/bin/mrjam-kanidm-worker-provision" <<'EOF'
    #!/bin/sh
    printf 'INVENTED_INERT_UNIT_STARTED\n' > /run/synthetic-provision-started
    EOF
    chmod 0555 "$out/bin/mrjam-kanidm-worker-provision"
  '';
  unit = pkgs.writeTextDir "mrjam-kanidm-worker-provision.service" ''
    [Unit]
    Description=Invented inert provisioning delivery fixture
    [Service]
    Type=oneshot
    ExecStart=${package}/bin/mrjam-kanidm-worker-provision
    StandardOutput=null
    StandardError=null
  '';
in if artifactsOnly then { inherit package unit; } else
assert bundle != null;
pkgs.testers.runNixOSTest {
  name = "mrjam-sealed-provision-delivery-import";
  requiredFeatures.kvm = true;
  globalTimeout = 600;
  nodes.machine = { ... }: {
    system.stateVersion = "26.05";
    virtualisation.memorySize = 768;
    virtualisation.cores = 1;
    virtualisation.diskSize = 3072;
    virtualisation.vlans = [ ];
    # A private store image excludes host paths; actual absence is asserted
    # before calling the real nix-store import operation inside the VM.
    virtualisation.useNixStoreImage = true;
    virtualisation.mountHostNixStore = false;
    virtualisation.writableStore = true;
    virtualisation.writableStoreUseTmpfs = false;
    environment.systemPackages = [ pkgs.nix pkgs.python3 ];
    environment.etc."delivery-fixture/receiver.py".source = ./deliver_provision.py;
    environment.etc."delivery-fixture/fixture.py".source = ./provision_delivery_fixture.py;
    environment.etc."delivery-fixture/bundle.json".source = bundle;
    environment.etc."delivery-fixture/synthetic-only".text = "INVENTED_INERT_DELIVERY_VM_ONLY\n";
  };
  testScript = ''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    result=json.loads(machine.succeed("python3 -I -S /etc/delivery-fixture/fixture.py",timeout=180))
    assert result["passed"] is True and len(result["checks"])==6
    result.update({
      "schema_version":1,
      "receiver_sha256":"${builtins.hashFile "sha256" ./deliver_provision.py}",
      "fixture_sha256":"${builtins.hashFile "sha256" ./provision_delivery_fixture.py}",
      "test_sha256":"${builtins.hashFile "sha256" ./provision-delivery-systemd.nix}",
      "bundle_sha256":"${builtins.hashFile "sha256" bundle}",
      "production_access":False,
      "limits":["Tiny invented inert package and unit only", "Production payload and target remain separately bound by the sealed receiver"]
    })
    Path(os.environ["out"],"result.json").write_text(json.dumps(result,sort_keys=True)+"\n")
  '';
}
