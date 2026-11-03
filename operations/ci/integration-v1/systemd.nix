{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  locked = import ../../forgejo/locked-toolchain.nix {};
  lib = pkgs.lib;
  public = builtins.fromJSON (builtins.readFile ./public-fixture-policy.json);
  sourceText = "invented source for Unix authority qualification only\n";
  manifest = builtins.toJSON { schema_version = 1; rules_revision = public.rules_revision;
    files = [{ path = "invented.txt"; bytes = builtins.stringLength sourceText; sha256 = builtins.hashString "sha256" sourceText; }]; };
  proposal = builtins.hashString "sha256" manifest;
  source = locked.runCommand "mrjam-authority-synthetic-source" {} ''
    mkdir -p "$out"
    cp ${locked.writeText "manifest.json" manifest} "$out/manifest.json"
    cp ${locked.writeText "invented.txt" sourceText} "$out/invented.txt"
  '';
  reportPolicy = locked.writeText "mrjam-invented-report-policy.json" (builtins.toJSON public);
  validator = locked.runCommand "mrjam-authority-invented-validator-not-deployable" { nativeBuildInputs = [ locked.makeWrapper ]; } ''
    mkdir -p "$out/bin" "$out/lib"
    cp ${./validator.py} "$out/lib/validator.py"
    substituteInPlace "$out/lib/validator.py" --replace-fail '@report-policy@' '${reportPolicy}'
    makeWrapper ${locked.python3}/bin/python3 "$out/bin/mrjam-validate" --add-flags '-I -S' --add-flags "$out/lib/validator.py"
  '';
  verifierClosure = locked.closureInfo { rootPaths = [ validator ]; };
  narHash = locked.runCommand "mrjam-invented-validator-nar-hash" {} ''
    ${locked.nix}/bin/nix-hash --type sha256 --base64 ${validator} > "$out"
  '';
  policy = public // {
    verifier = toString validator;
    verifier_nar_hash = "sha256-" + lib.removeSuffix "\n" (builtins.readFile narHash);
    closure_sha256 = builtins.hashString "sha256" (builtins.readFile "${verifierClosure}/store-paths");
    accepted_proposals = [ proposal ];
  };
  authorityV2 = args@{ config, lib, ... }: import ../authority-credentials-v2/module.nix (args // { pkgs = locked; });
in pkgs.testers.runNixOSTest {
  name = "mrjam-ci-distinct-identities-authority-and-coordinator";
  requiredFeatures.kvm = false;
  qemu.forceAccel = false;
  globalTimeout = 1200;
  nodes.machine = { config, lib, ... }:
  let
    authority = config.services.mrjamValidationAuthority.package;
    regularRunner = config.services.mrjamValidationCoordinatorAttestation.package;
    harness = regularRunner.overrideAttrs (old: {
      pname = "mrjam-ci-synthetic-go-task-harness";
      outputs = [ "out" "fixture" ];
      # The already qualified runner suite is not rerun. This build adds only
      # a named test entrypoint, executed under the actual unit below.
      doCheck = false;
      postPatch = (old.postPatch or "") + ''
        cp ${./runner-vm_test.go} internal/app/run/mrjam_systemd_vm_test.go
        substituteInPlace internal/app/run/mrjam_systemd_vm_test.go \
          --replace-fail '@rules@' '${public.rules_revision}' --replace-fail '@proposal@' '${proposal}'
      '';
      postBuild = (old.postBuild or "") + ''
        mkdir -p "$fixture/bin"
        go test -c -tags netgo,osusergo -o "$fixture/bin/mrjam-ci-synthetic-task" ./internal/app/run
      '';
    });
    testClosure = locked.closureInfo { rootPaths = [ harness.fixture ]; };
    testRoot = locked.runCommand "mrjam-ci-synthetic-coordinator-root" {} ''
      mkdir -p "$out"
      cp -a --reflink=auto ${config.services.mrjamValidationCoordinatorAttestation.root}/. "$out/"
      chmod u+w "$out" "$out/nix" "$out/nix/store"
      while IFS= read -r path; do
        if [ ! -e "$out$path" ]; then cp -a --reflink=auto "$path" "$out/nix/store/"; fi
      done < ${testClosure}/store-paths
    '';
    fixtureConfig = pkgs.writeText "mrjam-ci-synthetic-vm-bindings.json" (builtins.toJSON {
      inherit proposal policy;
      authority = toString authority;
      authority_policy = toString authority.policy;
      openssl = "${locked.openssl}/bin/openssl";
      systemctl = "${pkgs.systemd}/bin/systemctl";
      journalctl = "${pkgs.systemd}/bin/journalctl";
      diagnostic_signer = toString diagnosticSigner;
      python = "${locked.python3}/bin/python3";
      runuser = "${pkgs.util-linux}/bin/runuser";
      date = "${pkgs.coreutils}/bin/date";
      expected_root = toString testRoot;
      real_root = toString config.services.mrjamValidationCoordinatorAttestation.root;
      worker_source_sha256 = builtins.hashFile "sha256" ../../forgejo/worker.py;
    });
    diagnosticSigner = pkgs.runCommand "mrjam-ci-closed-signer-diagnostic.py" {} ''
      cp ${./diagnostic-signer.py} "$out"
      substituteInPlace "$out" --replace-fail '@authority@' '${authority}'
    '';
    readerProbe = pkgs.runCommand "mrjam-ci-synthetic-reader-probe.py" {} ''
      cp ${./reader-probe.py} "$out"
      substituteInPlace "$out" --replace-fail '@authority@' '${authority}'
    '';
    fixture = pkgs.runCommand "mrjam-ci-synthetic-unit-fixture" {} ''
      mkdir -p "$out"
      cp ${./fixture.py} "$out/fixture.py"
      substituteInPlace "$out/fixture.py" --replace-fail '@fixture-config@' '${fixtureConfig}'
    '';
  in {
    # The fixture pins v2 explicitly even while the parent composition is being
    # reviewed. Disable either scoped authority import to prevent duplicates.
    disabledModules = [
      { key = "mrjam-ci-locked:${toString ../authority-v1/module.nix}"; }
      { key = "mrjam-ci-locked:${toString ../authority-credentials-v2/module.nix}"; }
    ];
    imports = [ ../modules.nix authorityV2 ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1536;
    virtualisation.cores = 2;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    networking.nftables.enable = true;
    services.mrjamForgejoPolicy = { enable = true; mode = "plan"; phase = "operate-validation";
      rulesRevision = public.rules_revision; controllerRevision = "2222222222222222222222222222222222222222";
      tokenFile = "/run/synthetic-unused-governance-token"; };
    services.mrjamForgejoRunner = { enable = true; rulesRevision = public.rules_revision;
      coordinatorUid = policy.requester_uid; registrarUid = 61004;
      registrationTokenFile = "/run/synthetic-unused-registration-token"; };
    services.mrjamValidationWorker = { enable = true; rulesRevision = public.rules_revision; inherit validator; };
    services.mrjamValidationCollector = { enable = true; rulesRevision = public.rules_revision; };
    services.mrjamValidationStaging = { enable = true; proposals = [{ sha256 = proposal; inherit source; }]; };
    services.mrjamValidationAuthority = { enable = true; inherit policy; signingKeyFile = "/var/lib/mrjam-validation-authority/invented-key"; };
    services.mrjamValidationCoordinatorAttestation.enable = true;
    users.users.mrjam-validation-collector.uid = policy.collector_uid;
    users.users.mrjam-validation-worker.uid = 61005;
    users.groups.invented-outsider = {};
    users.users.invented-outsider = { isSystemUser = true; uid = 61006; group = "invented-outsider"; };
    systemd.services.mrjam-forgejo-runner.serviceConfig = {
      Type = lib.mkForce "oneshot";
      ExecStart = lib.mkOverride 40 "${harness.fixture}/bin/mrjam-ci-synthetic-task -test.run ^TestMRJAMSystemdBoundedChain$ -test.count=1";
      RootDirectory = lib.mkOverride 40 testRoot;
      # Keep stdout closed. Only the synthetic harness' own test output may be
      # inspected locally on failure; none is production/application output.
    };
    systemd.services.synthetic-credential-reader.serviceConfig = {
      Type = "oneshot";
      User = "mrjam-validation-authority";
      Group = "mrjam-validation-authority";
      ExecStart = "${locked.python3}/bin/python3 -I -S ${readerProbe}";
      # Unlike LoadCredential, a plain bind does not prepare the traversable
      # per-unit /run/credentials ancestor. Construct only this invented view.
      TemporaryFileSystem = [ "/run/credentials:mode=0755" ];
      BindReadOnlyPaths = [ "/var/lib/mrjam-ci-synthetic-observer/credential-view:/run/credentials/mrjam-validation-authority.service" ];
      NoNewPrivileges = true;
      CapabilityBoundingSet = "";
      ProtectSystem = "strict";
      ProtectHome = true;
      PrivateTmp = true;
      PrivateNetwork = true;
      StandardOutput = "journal";
      StandardError = "null";
      TimeoutStartSec = 10;
    };
    environment.etc."mrjam-ci-synthetic-fixture".text = "INVENTED_VM_ONLY\n";
    environment.etc."mrjam-ci-synthetic-bindings.json".source = fixtureConfig;
    environment.systemPackages = [ pkgs.python3 pkgs.util-linux locked.openssl ];
    system.build.mrjamCIUnitFixture = fixture;
  };
  testScript = { nodes, ... }: ''
    import json, os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    fixture = "${nodes.machine.system.build.mrjamCIUnitFixture}/fixture.py"
    checks = []
    for case in ("prepare", "inactive-boundaries", "fresh-chain", "cache-reuse", "wrong-peers", "key-separation", "legacy-cache-refused", "tamper-refused", "wrong-key-refused", "expiry-refused", "credential-reader-boundaries"):
      with subtest(case):
        try:
          observed = json.loads(machine.succeed("${pkgs.python3}/bin/python3 " + fixture + " " + case, timeout=150))
        except Exception:
          if case == "fresh-chain":
            print(machine.execute("${pkgs.python3}/bin/python3 " + fixture + " diagnose-signer", timeout=40)[1])
          raise
        assert observed == {"case": case, "status": "passed"}, observed
        checks.append(case)
    machine.succeed("systemctl stop mrjam-forgejo-runner.service mrjam-validation-authority.socket mrjam-validation-authority.service mrjam-validation-export.socket mrjam-validation-collector.socket mrjam-validation-worker.socket")
    Path(os.environ["out"], "result.json").write_text(json.dumps({
      "schema_version": 1, "checks": checks, "production_access": False,
      "scope": "real-systemd-distinct-identities-synthetic-admitted-task",
      "authority_v1_sources_preserved": True, "authority_v2_fixed_credential_reader": True, "coordinator_sources_unchanged": True,
      "substitutions": ["Synthetic immutable validator and source/report, no application compilation", "Admitted task delivered by a Go test entrypoint instead of Forgejo API/daemon", "Test entrypoint closure added to the otherwise unchanged private coordinator root", "Invented key/UIDs/credentials only"],
      "not_established": ["Actual Forgejo job transport", "Production identities/key/policy/capacity", "New validator execution on every job", "Human review/merge/deployment authority"]
    }, sort_keys=True) + "\n")
  '';
}
