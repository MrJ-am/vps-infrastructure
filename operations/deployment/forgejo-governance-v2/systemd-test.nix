{ nixpkgs, acceleration ? "kvm" }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  locked = import ../../forgejo/locked-toolchain.nix { };
  forgejo = locked.forgejo;
  bootstrap = pkgs.callPackage ../forgejo-bootstrap/package.nix { forgejoUid = 982; forgejoGid = 982; };
  seed = pkgs.runCommand "invented-full-history-governance-bundle" { nativeBuildInputs = [ pkgs.git pkgs.python3 ]; } ''
    mkdir -p "$out"
    export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
    export GIT_AUTHOR_NAME=Invented GIT_AUTHOR_EMAIL=invented@example.invalid
    export GIT_COMMITTER_NAME=Invented GIT_COMMITTER_EMAIL=invented@example.invalid
    export GIT_AUTHOR_DATE=2000-01-01T00:00:00Z GIT_COMMITTER_DATE=2000-01-01T00:00:00Z
    git init --initial-branch=main source
    cd source
    echo 'invented original source' > README.txt
    git add README.txt
    git commit -m 'invented original source'
    git rev-parse HEAD > "$out/first"
    git tag v1
    echo 'invented accepted source' > README.txt
    git commit -am 'invented accepted source'
    git rev-parse HEAD > "$out/accepted"
    git branch original-history
    # Forgejo hook batches at 30 references. The old three-branch fixture
    # accidentally put main in that first batch and concealed this defect.
    for number in $(seq -w 1 48); do
      git branch "synthetic-history-$number"
    done
    git checkout -b future-proposal
    echo 'invented future proposal' > README.txt
    git commit -am 'invented future proposal'
    git rev-parse HEAD > "$out/future"
    git checkout main
    git bundle create "$out/source.bundle" --branches --tags
    git for-each-ref '--format=%(objectname) %(refname)' refs/heads refs/tags > "$out/refs"
  '';
  binding = pkgs.runCommand "invented-governance-binding" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    mkdir -p "$out"
    python3 - ${seed} "$out/binding.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
seed=Path(sys.argv[1]);target=Path(sys.argv[2])
refs={line.split(' ',1)[1]:line.split(' ',1)[0] for line in (seed/'refs').read_text().splitlines()}
main=(seed/'accepted').read_text().strip()
names=('Signature','apprendre-a-demontrer','etp-vie-affective','matheval','mrjam-plateforme','mrjam-validation','style-mrjam','vision','vps-infrastructure')
value={'schema_version':1,'owner':'MrJ-am','forgejo_version':'17.0.1','rules_revision':main,'controller_revision':main,
       'metadata_disposition':'existing-forgejo-preserved-github-lfs-and-collaboration-retained',
       'repositories':{name:{'source':'reviewed-bundle','bundle':'/var/lib/mrjam-source-import/'+name+'.bundle',
                            'bundle_sha256':hashlib.sha256((seed/'source.bundle').read_bytes()).hexdigest(),
                            'refs_sha256':hashlib.sha256(json.dumps(refs,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                            'main':main} for name in names}}
target.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')
PY
  '';
  package = pkgs.callPackage ./package.nix {
    bindingFile = "${binding}/binding.json";
    bindingSha256 = builtins.hashFile "sha256" "${binding}/binding.json";
  };
in assert builtins.elem acceleration [ "kvm" "tcg" ]; pkgs.testers.runNixOSTest {
  name = "mrjam-forgejo-initial-default-branch-adoption-v2";
  requiredFeatures.kvm = acceleration == "kvm";
  qemu.forceAccel = acceleration == "kvm";
  globalTimeout = 1200;
  nodes.machine = { config, lib, pkgs, ... }: {
    imports = [ ../../nixos/mrjam-forgejo-host.nix ../forgejo-bootstrap/module.nix ];
    system.stateVersion = "26.05";
    networking.hostName = "srv1982677";
    virtualisation.memorySize = 1536; virtualisation.cores = 2; virtualisation.diskSize = 4096;
    virtualisation.qemu.options = [ "-machine accel=${acceleration}" ];
    virtualisation.qemu.networkingOptions = lib.mkForce [ ]; virtualisation.vlans = [ ];
    networking.useDHCP = lib.mkForce false; networking.dhcpcd.enable = false;
    services.mrjamForgejoHost = { enable = true; uid = 982; gid = 982;
      artifactStorePath = builtins.unsafeDiscardStringContext "${forgejo}"; };
    services.postgresql = { enable = true; package = pkgs.postgresql_17;
      ensureDatabases = [ "forgejo" ]; ensureUsers = [{ name = "forgejo"; ensureDBOwnership = true; }]; };
    environment.systemPackages = [ package bootstrap forgejo pkgs.postgresql_17 pkgs.git pkgs.python3 pkgs.curl pkgs.util-linux ];
    environment.variables = {
      SYNTHETIC_BOOTSTRAP_PACKAGE = "${bootstrap}"; SYNTHETIC_FORGEJO_PACKAGE = "${forgejo}";
      SYNTHETIC_GOVERNANCE_PACKAGE = "${package}"; SYNTHETIC_GOVERNANCE_BINDING = "${binding}/binding.json";
      SYNTHETIC_GOVERNANCE_SEED = "${seed}";
    };
    environment.etc."synthetic-forgejo.ini".source = (pkgs.formats.ini { }).generate "synthetic-forgejo.ini"
      (lib.recursiveUpdate config.services.mrjamForgejoHost.settings {
        security = { SECRET_KEY = "SYNTHETIC-SECRET-KEY-NOT-PRODUCTION"; INTERNAL_TOKEN = "SYNTHETIC-INTERNAL-TOKEN-NOT-PRODUCTION"; };
        oauth2.JWT_SECRET = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
      });
    environment.etc."forgejo-adopt-runtime-role.sql".source = ../../forgejo/adopt-runtime-role.sql;
    environment.etc."synthetic-forgejo-policy/reconcile.py".source = ../../forgejo/reconcile.py;
    environment.etc."forgejo-bootstrap-fixture.py".source = ../forgejo-bootstrap/fixture.py;
    environment.etc."forgejo-governance-fixture.py".source = ./fixture.py;
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql-setup.service")
    fixture = "python3 -B /etc/forgejo-governance-fixture.py "
    checks=[]
    with subtest("private fixed source staging and read-only preflight"):
        machine.succeed("python3 -B /etc/forgejo-bootstrap-fixture.py prepare")
        machine.succeed("systemctl start forgejo.service")
        machine.wait_for_open_port(3004)
        machine.succeed("systemctl start mrjam-forgejo-bootstrap.service")
        machine.succeed(fixture+"prepare")
        checks.append("nine-private-staged-bundles-hash-bound-probe-before-adoption")
    with subtest("closed entry rejects absent durable adoption phase"):
        machine.succeed(fixture+"absent-phase")
        checks.append("no-adoption-without-durable-checkpoint-no-token-retained")
    with subtest("initial existing private repository history and unrelated metadata"):
        machine.succeed(fixture+"seed-existing")
        checks.append("real-scoped-token-git-http-with-password-login-disabled")
    with subtest("real empty repository chooses imported archive and strict v1 contract refuses"):
        machine.succeed(fixture+"reproduce-default")
        checks.append("real-atomic-multiref-import-reproduces-default-branch-adoption-required")
    with subtest("actual nine repository adoption and exact main protection"):
        machine.succeed(fixture+"adopt")
        checks.append("nine-real-sources-default-main-adopted-only-from-empty-protected-and-token-revoked")
    with subtest("drained asynchronous updates retain main and all protection"):
        machine.succeed(fixture+"drain")
        checks.append("drained-postreceive-and-repeated-default-main-protection-readback")
    with subtest("idempotence preserves histories tags and unrelated repository"):
        machine.succeed(fixture+"replay")
        checks.append("replay-preserves-existing-history-tag-objects-and-unrelated-repository")
    with subtest("existing protected main cannot be bypassed by technical admin"):
        machine.succeed(fixture+"protected-refusal")
        checks.append("real-fast-forward-push-to-protected-main-refused-even-for-admin")
    with subtest("private source never enters an already public repository"):
        machine.succeed(fixture+"private-target")
        checks.append("private-source-public-target-refused-before-any-source-write")
    with subtest("tampered private source input refuses before a credential lease"):
        machine.succeed(fixture+"tamper")
        checks.append("changed-source-bytes-refused-and-all-temporary-tokens-revoked")
    Path(os.environ["out"],"forgejo-governance-result.json").write_text(json.dumps({
        "schema_version":1,"scope":"isolated-invented-forgejo17-postgresql17-git-http","checks":checks,
        "package":"${package}","forgejo":"${forgejo}","bootstrap":"${bootstrap}",
        "binding_sha256":"${builtins.hashFile "sha256" "${binding}/binding.json"}",
        "core_sha256":"${builtins.hashFile "sha256" ./core.py}",
        "credentials_sha256":"${builtins.hashFile "sha256" ./credentials.py}",
        "entry_sha256":"${builtins.hashFile "sha256" ./entry.py}",
        "fixture_sha256":"${builtins.hashFile "sha256" ./fixture.py}",
        "test_sha256":"${builtins.hashFile "sha256" ./systemd-test.nix}",
        "production_access":False,"production_source_binding":False,
        "limits":["Invented Git histories only","No production bundle or accepted rules authority inferred","No runners or human review identities provisioned"]
    },sort_keys=True)+"\n")
  '';
}
