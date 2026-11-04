{ nixpkgs ? /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  locked = import ../../forgejo/locked-toolchain.nix {};
  forgejo = locked.forgejo;
  bootstrap = pkgs.callPackage ../../deployment/forgejo-bootstrap/package.nix { forgejoUid = 982; forgejoGid = 982; };
  seed = pkgs.runCommand "invented-rules-bootstrap-proposal" { nativeBuildInputs = [ pkgs.git pkgs.python3 ]; } ''
    mkdir -p "$out"
    export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
    export GIT_AUTHOR_NAME=Invented GIT_AUTHOR_EMAIL=invented@example.invalid
    export GIT_COMMITTER_NAME=Invented GIT_COMMITTER_EMAIL=invented@example.invalid
    export GIT_AUTHOR_DATE=2000-01-01T00:00:00Z GIT_COMMITTER_DATE=2000-01-01T00:00:00Z
    git init --initial-branch=main source
    cd source
    echo 'invented rules source' > README
    git add README
    git commit -m 'invented rules base'
    git rev-parse HEAD > "$out/base"
    git bundle create --version=2 "$out/baseline.bundle" refs/heads/main
    mkdir -p .forgejo/workflows
    cp ${../../forgejo/independent-validation.yml} .forgejo/workflows/independent-validation.yml
    git add .forgejo/workflows/independent-validation.yml
    git commit -m 'invented workflow addition'
    git rev-parse HEAD > "$out/head"
    git rev-parse 'HEAD^{tree}' > "$out/tree"
    python3 - "$out" <<'PY'
import hashlib,json,subprocess,sys
from pathlib import Path
p=Path(sys.argv[1]);base=(p/'base').read_text().strip();head=(p/'head').read_text().strip();tree=(p/'tree').read_text().strip()
ref='refs/heads/bootstrap-ci-workflow-'+head[:16]
subprocess.run(['git','update-ref',ref,head],check=True)
subprocess.run(['git','bundle','create','--version=2',str(p/'proposal.bundle'),ref,'^'+base],check=True)
raw=(p/'proposal.bundle').read_bytes()
value=dict(schema_version=1,base=base,head=head,tree=tree,
 workflow_sha256=hashlib.sha256(Path('.forgejo/workflows/independent-validation.yml').read_bytes()).hexdigest(),
 bundle_sha256=hashlib.sha256(raw).hexdigest(),bundle_bytes=len(raw),evidence_sha256='a'*64)
(p/'binding.json').write_text(json.dumps(value,sort_keys=True)+'\n')
PY
  '';
  proposalPackage = pkgs.callPackage ../rules-proposal-v1/package.nix { bindingFile = "${seed}/binding.json";
    bindingSha256 = builtins.hashFile "sha256" "${seed}/binding.json"; };
  package = pkgs.callPackage ./package.nix { inherit proposalPackage; };
in pkgs.testers.runNixOSTest {
  name = "mrjam-rules-bootstrap-adoption-native-review-fast-forward";
  requiredFeatures.kvm = true;
  globalTimeout = 900;
  nodes.machine = { config, lib, ... }: {
    imports = [ ../../nixos/mrjam-forgejo-host.nix ../../deployment/forgejo-bootstrap/module.nix ];
    system.stateVersion = "26.05";
    networking.hostName = "srv1982677";
    virtualisation.memorySize = 1536; virtualisation.cores = 2; virtualisation.diskSize = 4096;
    virtualisation.qemu.networkingOptions = lib.mkForce []; virtualisation.vlans = [];
    networking.useDHCP = lib.mkForce false; networking.dhcpcd.enable = false;
    services.mrjamForgejoHost = { enable = true; uid = 982; gid = 982;
      artifactStorePath = builtins.unsafeDiscardStringContext "${forgejo}"; };
    services.postgresql = { enable = true; package = pkgs.postgresql_17;
      ensureDatabases = [ "forgejo" ]; ensureUsers = [{ name = "forgejo"; ensureDBOwnership = true; }]; };
    environment.systemPackages = [ package bootstrap forgejo pkgs.postgresql_17 pkgs.git pkgs.python3 pkgs.util-linux ];
    environment.variables = { SYNTHETIC_BOOTSTRAP_PACKAGE = "${bootstrap}"; SYNTHETIC_FORGEJO_PACKAGE = "${forgejo}";
      SYNTHETIC_PROPOSAL_PACKAGE = "${proposalPackage}"; SYNTHETIC_ADOPTION_PACKAGE = "${package}"; SYNTHETIC_PROPOSAL_SEED = "${seed}";
      SYNTHETIC_PROPOSAL_BINDING = "${seed}/binding.json"; SYNTHETIC_GIT = "${pkgs.git}/bin/git"; };
    environment.etc."synthetic-forgejo.ini".source = (pkgs.formats.ini {}).generate "synthetic-forgejo.ini"
      (lib.recursiveUpdate config.services.mrjamForgejoHost.settings {
        security = { SECRET_KEY = "SYNTHETIC-SECRET-KEY-NOT-PRODUCTION"; INTERNAL_TOKEN = "SYNTHETIC-INTERNAL-TOKEN-NOT-PRODUCTION"; };
        oauth2.JWT_SECRET = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
      });
    environment.etc."forgejo-adopt-runtime-role.sql".source = ../../forgejo/adopt-runtime-role.sql;
    environment.etc."synthetic-forgejo-policy/reconcile.py".source = ../../forgejo/reconcile.py;
    environment.etc."forgejo-bootstrap-fixture.py".source = ../../deployment/forgejo-bootstrap/fixture.py;
    environment.etc."rules-proposal-fixture.py".source = ../rules-proposal-v1/fixture.py;
    environment.etc."rules-adoption-fixture.py".source = ./fixture.py;
    environment.etc."review-projection-fixture/contract.py".source = ../authority-v1/contract.py;
    environment.etc."review-projection-fixture/signer.py".source = ../authority-v1/signer.py;
    environment.etc."review-projection-fixture/collector.py".source = ../authority-v1/collector.py;
    environment.etc."review-projection-fixture/review_contract.py".source = ../review-v1/review_contract.py;
    environment.etc."review-projection-fixture/api_projection.py".source = ../review-v1/api_projection.py;
    environment.etc."review-projection-fixture/read_transport.py".source = ../review-v1/read_transport_v2.py;
  };
  testScript = ''
    import json,os
    from pathlib import Path
    start_all()
    machine.wait_for_unit('postgresql-setup.service')
    fixture='python3 -B /etc/rules-adoption-fixture.py '
    checks=[]
    with subtest('invented private proposal with retained native SSO identity'):
        machine.succeed('python3 -B /etc/forgejo-bootstrap-fixture.py prepare')
        machine.succeed('systemctl start forgejo.service')
        machine.wait_for_open_port(3004)
        machine.succeed('systemctl start mrjam-forgejo-bootstrap.service')
        machine.succeed('python3 -B /etc/rules-proposal-fixture.py prepare')
        machine.succeed('python3 -B /etc/rules-proposal-fixture.py open')
        machine.succeed(fixture+'identity')
        checks.append('native-sso-unique-owner-derived-ambiguity-and-invalid-provider-refused')
    with subtest('no real human review means no merge request or checkpoint'):
        machine.succeed(fixture+'missing')
        checks.append('absent-review-refused-before-native-merge-and-token-revoked')
    with subtest('native review API supplies the exact independent approval'):
        machine.succeed(fixture+'review')
        machine.copy_from_vm('/var/lib/synthetic-forgejo-proof/explicit-tree-resolution.json',os.environ['out'])
        machine.copy_from_vm('/var/lib/synthetic-forgejo-proof/bootstrap-review.json',os.environ['out'])
        machine.copy_from_vm('/var/lib/synthetic-forgejo-proof/native-review-participants.json',os.environ['out'])
        checks.append('actual-native-review-shape-official-approval-exact-head-and-text')
    with subtest('repo-scoped native bootstrap merge preserves protection without CI status'):
        machine.succeed(fixture+'adopt')
        checks.append('native-repo-scoped-force-merge-fast-forward-main-only-no-status-policy-unchanged')
    with subtest('replay observes the same merged PR and retained review'):
        machine.succeed(fixture+'replay')
        checks.append('idempotent-postmerge-observation-no-second-merge')
    Path(os.environ['out'],'result.json').write_text(json.dumps({
      'schema_version':1,'checks':checks,'package':'${package}','proposal_package':'${proposalPackage}',
      'forgejo':'${forgejo}',
      'adoption_sha256':'${builtins.hashFile "sha256" ./adoption.py}',
      'identity_sha256':'${builtins.hashFile "sha256" ./identity.py}',
      'merge_transport_sha256':'${builtins.hashFile "sha256" ./merge_transport.py}',
      'production_access':False,'human_production_review_created':False,
      'limits':['Invented Git history, SSO subject/account and native API review only',
                'Native helper core exercised directly; entry gate inherited from sealed proposal entry',
                'No atomicity claimed across independent human review changes; postmerge drift withholds authority',
                'No CI status, attestation, protection change or activation']
    },sort_keys=True)+'\n')
  '';
}
