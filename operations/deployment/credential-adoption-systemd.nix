{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  stage = pkgs.writeText "stage-synthetic-worker-credentials.py" ''
    import importlib.util, json, os
    from pathlib import Path
    spec=importlib.util.spec_from_file_location("stage", "${./stage_credentials.py}")
    stage=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    root=Path("/var/lib/mrjam-identite")
    root.mkdir(mode=0o700,exist_ok=True)
    smtp={"host":"smtp.protonmail.ch","port":587,"username":"invented@example.invalid",
          "password":"OnlyInventedFixture123456","from_address":"invented@example.invalid",
          "starttls_required":True,"certificate_verification":True}
    cycle={"recipient_age":"age1"+"q"*58,"adresse_exploitant":"archive@example.invalid"}
    for name,value in (("proton-smtp.json",json.dumps(smtp)),("cycle.json",json.dumps(cycle)),("fermeture-hook.secret","C"*43+"\n")):
        path=root/name
        path.write_text(value)
        path.chmod(0o600)
    stage.prepare()
    for name in stage.FILES:
        original=root/name
        result=stage.OUTPUT/name
        assert result.read_bytes()==original.read_bytes()
        assert (result.stat().st_uid,result.stat().st_gid,result.stat().st_mode&0o777,result.stat().st_nlink)==(0,0,0o440,1)
    assert stage.OUTPUT.stat().st_mode&0o777==0o700
    try:
        stage.prepare()
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing staging replaced")
  '';
  negative = pkgs.writeText "refuse-synthetic-credential-inputs.py" ''
    import importlib.util, os, tempfile
    from pathlib import Path
    spec=importlib.util.spec_from_file_location("stage", "${./stage_credentials.py}")
    stage=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    with tempfile.TemporaryDirectory() as name:
        root=Path(name)
        source=root/"source"; source.mkdir(mode=0o700)
        target=root/"target"; target.mkdir(mode=0o700)
        path=source/"proton-smtp.json"
        src=stage.directory(source); dst=stage.directory(target)
        try:
            for case in ("public", "hardlink", "symlink", "fifo", "oversized", "empty", "owner"):
                outside=root/"outside"
                if case=="fifo":
                    os.mkfifo(path,0o600)
                elif case=="symlink":
                    outside.write_bytes(b"SYNTHETIC"); outside.chmod(0o600); path.symlink_to(outside)
                else:
                    path.write_bytes(b"" if case=="empty" else b"x"*65537 if case=="oversized" else b"SYNTHETIC")
                    path.chmod(0o644 if case=="public" else 0o600)
                    if case=="hardlink": os.link(path,outside)
                    if case=="owner": os.chown(path,65534,0)
                try:
                    stage.copy_file(src,dst,"proton-smtp.json")
                except (stage.Refused,OSError):
                    pass
                else:
                    raise AssertionError("unsafe fixture accepted")
                assert not (target/"proton-smtp.json").exists()
                path.unlink(); outside.unlink(missing_ok=True)
            (root/"link").symlink_to(source)
            try:
                stage.directory(root/"link")
            except OSError:
                pass
            else:
                raise AssertionError("parent symlink accepted")
        finally:
            os.close(src); os.close(dst)
  '';
  verify = pkgs.writeText "verify-synthetic-adapted-credentials.py" ''
    import base64, hashlib, json, os, stat
    from pathlib import Path
    root=Path("/var/lib/mrjam-worker-credentials/v1")
    expected={"smtp.json","recipient","closure","approval","archive.json","archive-initialize.json"}
    assert {p.name for p in root.iterdir()}==expected
    assert root.stat().st_mode&0o777==0o700
    for p in root.iterdir():
        item=p.lstat()
        assert stat.S_ISREG(item.st_mode) and (item.st_uid,item.st_gid,item.st_nlink,item.st_mode&0o777)==(0,0,1,0o600)
    smtp=json.loads((root/"smtp.json").read_bytes())
    assert smtp==json.loads(Path("/var/lib/mrjam-identite/proton-smtp.json").read_bytes())
    assert (root/"recipient").read_bytes()==b"archive@example.invalid\n"
    assert (root/"closure").read_bytes()==b"C"*43+b"\n"
    approval=(root/"approval").read_bytes()
    assert len(base64.urlsafe_b64decode(approval.strip()+b"="))==32
    assert approval!=(root/"closure").read_bytes()
    for suffix in ("","-initialize"):
        conf=json.loads((root/("archive"+suffix+".json")).read_bytes())
        assert conf["age_recipient"]=="age1"+"q"*58
        assert conf["journal_database"]=="vision_journal"
        assert conf["smtp_file"]=="/run/credentials/mrjam-vision-archive"+suffix+".service/smtp"
        assert Path(conf["age_program"]).is_file()
    marker=Path("/run/synthetic-credential-fingerprints.json")
    observed={p.name:[p.stat().st_ino,p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()] for p in root.iterdir()}
    if marker.exists():
        assert json.loads(marker.read_text())==observed
    else:
        marker.write_text(json.dumps(observed))
        marker.chmod(0o600)
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-worker-credential-adoption-systemd";
  requiredFeatures.kvm = true;
  globalTimeout = 300;
  nodes.machine = { ... }: {
    imports = [ ./credential-adoption.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 768;
    virtualisation.cores = 1;
    virtualisation.vlans = [ ];
    environment.systemPackages = [ pkgs.python3 ];
  };
  testScript = ''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    unit="mrjam-worker-credentials-adapt.service"
    checks=[]
    with subtest("the installed unit never starts on its own"):
        machine.fail("systemctl is-active --quiet "+unit)
        assert machine.succeed("systemctl show --value -p StandardOutput "+unit).strip()=="null"
        assert machine.succeed("systemctl show --value -p StandardError "+unit).strip()=="null"
        machine.fail("test -d /var/lib/mrjam-worker-credentials/v1")
        checks.append("explicit-only-closed-diagnostics")
    with subtest("unsafe invented sources fail before copying"):
        machine.succeed("python3 -I -S ${negative}",timeout=30)
        checks.append("links-fifo-permissions-size-owner-refused")
    with subtest("private staging preserves exact source bytes and refuses overwrite"):
        machine.succeed("python3 -I -S ${stage}")
        checks.append("private-staging-exact-and-no-overwrite")
    with subtest("the real unit adapts its readonly inputs with no network"):
        machine.succeed("systemctl start "+unit)
        machine.succeed("python3 -I -S ${verify}")
        checks.append("real-unit-private-outputs-and-consumer-paths")
    with subtest("repeating does not rotate approval or replace any output"):
        machine.succeed("systemctl start "+unit)
        machine.succeed("python3 -I -S ${verify}")
        checks.append("repeat-preserves-all-output-bytes-and-inodes")
    with subtest("altered input fails closed and retains the original generation"):
        machine.succeed("chmod 0600 /run/mrjam-worker-credential-adaptation/cycle.json")
        machine.fail("systemctl start "+unit)
        machine.succeed("python3 -I -S ${verify}")
        # The synthetic sentinel must never be recorded by the tested unit.
        unit_journal=machine.succeed("journalctl -u "+unit+" --no-pager")
        assert "OnlyInventedFixture123456" not in unit_journal and "archive@example.invalid" not in unit_journal
        checks.append("invalid-source-retains-generation-and-closed-log")
    Path(os.environ["out"],"result.json").write_text(json.dumps({
      "schema_version":1,"checks":checks,"production_access":False,
      "stage_sha256":"${builtins.hashFile "sha256" ./stage_credentials.py}",
      "unit_sha256":"${builtins.hashFile "sha256" ./credential-adoption.nix}",
      "test_sha256":"${builtins.hashFile "sha256" ./credential-adoption-systemd.nix}",
      "limits":["All credentials invented; no production SMTP connection or real mail"]
    },sort_keys=True)+"\n")
  '';
}
