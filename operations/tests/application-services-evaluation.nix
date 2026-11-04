# Structural checks use invented bindings only. They are not installed-state,
# runtime-ready, TLS-renewal or deployment qualification.
{ nixpkgs, output ? "checks" }:
let
  lib = import (nixpkgs + "/lib");
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  identityNames = [ "mrjam-rust-blue" "mrjam-rust-green" "mrjam-vision-admission"
    "mrjam-vision-archive" "mrjam-vision-closure" "mrjam-vision-cycle" "mrjam-vision-replay" ];
  synthetic = {
    enable = true;
    # Existing public store roots are enough to evaluate unit declarations. No
    # fixture pretends these two directories contain a runtime.json or are ready.
    slots = { blue = toString nixpkgs; green = toString nixpkgs; };
    identities = builtins.listToAttrs (lib.imap0 (index: name:
      lib.nameValuePair name { uid = 42000 + index; gid = 42000 + index; }) identityNames);
    sites = lib.mapAttrs (_: host: { inherit host; certificateName = host; }) {
      audition = "audition.mrj.am"; log = "log.mrj.am"; logique = "logic.example.invalid";
      logo = "logo.example.invalid"; mateval = "principiipetit.io";
      style = "style.example.invalid"; vision = "vision.mrj.am";
    };
    databaseAccess = {
      mateval = { database = "mateval_synthetic"; role = "mateval_app_synthetic"; };
      matevalAdministration = { database = "mateval_synthetic"; role = "mateval_admin_synthetic"; };
      vision = { database = "vision_synthetic"; role = "vision_synthetic"; };
      visionAdministration = { database = "vision_synthetic"; role = "vision_administration"; };
      visionJournal = { database = "journal_synthetic"; role = "vision_journal_writer"; };
      audition = { database = "audition_synthetic"; role = "audition_synthetic"; };
    };
    admissionApprovalCredentialFile = "/var/lib/mrjam/secrets/synthetic-approval";
    principiiRoot = "/srv/synthetic-public-site";
    workers = {
      enable = true;
      visionDatabase = "vision_synthetic"; journalDatabase = "journal_synthetic";
      ageRecipient = "age1" + lib.concatStrings (lib.replicate 58 "q");
      credentials = lib.genAttrs [ "smtp" "archiveRecipient" "cycleIdentity" "replayIdentity" "admissionIdentity" "closure" "approval" ]
        (name: "/var/lib/mrjam/secrets/synthetic-${name}");
    };
  };
  certificate = {
    domain = "vision.mrj.am"; extraDomains = [ ];
    accountHash = "0123456789abcdef0123"; certificateHash = "0123456789abcdef4567";
    server = "https://acme.example.invalid/directory"; keyType = "ec256";
    webroot = "/var/lib/synthetic-acme"; interval = "daily"; jitter = "24h";
  };
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../hosts/mrjam-vps/core-services.nix
      ../hosts/mrjam-vps/application-services.nix ../hosts/mrjam-vps/renewal.nix {
        system.stateVersion = "26.05";
        fileSystems."/" = { device = "/dev/synthetic"; fsType = "ext4"; };
        boot.loader.grub.enable = false;
        users.groups.mrjam-log-readers.gid = 42020;
        mrjamVpsApplications = synthetic;
        mrjamVpsRenewal = { enable = true; certificates."vision.mrj.am" = certificate; };
      } extra ];
  }).config;
  cfg = evaluate { };
  vhost = cfg.services.nginx.virtualHosts;
  renewal = cfg.systemd.services."mrjam-acme-renew-vision.mrj.am";
  colliding = evaluate { mrjamVpsApplications.identities.mrjam-rust-blue.uid = lib.mkForce 982; };
  promotedWorker = evaluate { systemd.services.mrjam-vision-admission.wantedBy = [ "multi-user.target" ]; };
  duplicatedAcme = evaluate { security.acme.certs."other.example.invalid" = { }; };
  existingSites = evaluate {
    mrjamVpsApplications.sites = lib.mkForce (builtins.removeAttrs synthetic.sites [ "style" "logo" ]);
    mrjamVpsApplications.principiiRoot = lib.mkForce null;
  };
  refused = prefix: value: lib.any (assertion: !assertion.assertion && lib.hasPrefix prefix assertion.message) value.assertions;
  result = {
    validComposition = lib.all (assertion: assertion.assertion) cfg.assertions;
    exactSevenFrontends = builtins.length (builtins.attrNames cfg.mrjamVpsApplications.sites) == 7;
    existingSitesWithoutInventedDemoDomains = lib.all (a: a.assertion) existingSites.assertions
      && !(existingSites.services.nginx.virtualHosts ? "style.example.invalid")
      && !(existingSites.services.nginx.virtualHosts ? "logo.example.invalid");
    allSevenArtifactsRetained = lib.all (name: builtins.elem
      (builtins.storePath existingSites.mrjamVpsApplications.frontendStorePaths.${name})
      existingSites.system.extraDependencies) [ "audition" "log" "logique" "logo" "mateval" "style" "vision" ];
    originalRootRedirectPreserved = existingSites.services.nginx.virtualHosts."principiipetit.io".root == null
      && existingSites.services.nginx.virtualHosts."principiipetit.io".locations."= /".return == "308 /matheval/";
    wwwAliasPreserved = vhost."www.principiipetit.io".locations."/".return == "308 https://principiipetit.io$request_uri";
    noVise = !(cfg.systemd.services ? vise) && !(vhost ? "vise.mrj.am");
    allApplicationIdentitiesFixed = lib.all (name: cfg.users.users.${name}.uid == synthetic.identities.${name}.uid
      && cfg.users.groups.${name}.gid == synthetic.identities.${name}.gid) identityNames;
    retainedIdentityCollisionRefused = refused "mrjamVpsApplications: dedicated numeric" colliding;
    noImplicitApplicationPromotion = lib.all (name: cfg.systemd.services.${name}.wantedBy == [ ]) identityNames;
    legacyIdentityWorkerPromotionRefused = refused "mrjamVpsApplications: legacy-protocol" promotedWorker;
    noWorkerTimers = !cfg.services.mrjamVisionArchive.timer.enable
      && !cfg.services.mrjamVisionCycle.timer.enable && !cfg.services.mrjamVisionReplay.timer.enable;
    newerArchiveSelected = cfg.services.mrjamVisionArchive.artifactStorePath == cfg.mrjamVpsApplications.workers.artifacts.archive
      && lib.hasInfix "7d87768bd141-archive" cfg.services.mrjamVisionArchive.artifactStorePath;
    closureKeepsPrivatePort = lib.hasInfix "serve" cfg.systemd.services.mrjam-vision-closure.serviceConfig.ExecStart;
    matevalPrefixPreserved = vhost."principiipetit.io".locations."^~ /matheval/".proxyPass == "http://127.0.0.1:38101"
      && vhost."principiipetit.io".root == "/srv/synthetic-public-site";
    logFrontendAndNativeApis = vhost."log.mrj.am".locations."/".proxyPass == "http://127.0.0.1:38101"
      && vhost."log.mrj.am".locations."^~ /v1/".proxyPass == "https://127.0.0.1:8443"
      && lib.hasInfix "proxy_ssl_verify on;" vhost."log.mrj.am".locations."^~ /oauth2/".extraConfig;
    nativeAdminBoundariesRetained = lib.all (path: vhost."log.mrj.am".locations."^~ ${path}".return == "404")
      [ "/v1/raw/" "/v1/oauth2/" "/v1/service_account/" "/scim/" ];
    logEntryQueryRetained = lib.all (path: vhost."log.mrj.am".locations."= ${path}".proxyPass == "http://127.0.0.1:38101/index.html")
      [ "/ui/oauth2" "/ui/reset" ];
    mcpRevocationRetained = lib.all (host: vhost.${host}.locations."= /oauth/revoke".proxyPass == "http://127.0.0.1:3002")
      [ "vision.mrj.am" "audition.mrj.am" ];
    sessionsNotMountedIntoRust = cfg.systemd.services.mrjam-rust-blue.serviceConfig.BindReadOnlyPaths == [ "/run/mrjam-identity" ]
      && cfg.systemd.services.mrjam-rust-blue.serviceConfig.SupplementaryGroups == [ "mrjam-log-readers" ];
    runtimeCredentialsKeepOriginalActivationReference = builtins.elem
      "mateval-activation-sha256:/var/lib/mrjam-metier/secrets/matheval-setup-hash"
      cfg.systemd.services.mrjam-rust-blue.serviceConfig.LoadCredential;
    noSqlBootstrap = cfg.services.postgresql.ensureDatabases == [ ] && cfg.services.postgresql.ensureUsers == [ ];
    acmeIdentityRetained = cfg.users.users.acme.uid == 996 && cfg.users.groups.acme.gid == 995;
    existingAcmeDirectoriesPinned = builtins.elem "/var/lib/acme/.lego/accounts/0123456789abcdef0123:/tmp/accounts" renewal.serviceConfig.BindReadOnlyPaths
      && builtins.elem "/var/lib/acme/.lego/vision.mrj.am/0123456789abcdef4567:/tmp/certificates" renewal.serviceConfig.BindPaths;
    noAcmeBootstrapDirectories = !(renewal.serviceConfig ? StateDirectory);
    noAcmeAutoPromotion = cfg.systemd.timers."mrjam-acme-renew-vision.mrj.am".wantedBy == [ ];
    renewalOnly = lib.hasInfix "renew --no-random-sleep --dynamic" renewal.script
      && !(lib.hasInfix " run " renewal.script) && !(lib.hasInfix "--email" renewal.script);
    noAcmeSecretLogs = renewal.serviceConfig.StandardOutput == "null" && renewal.serviceConfig.StandardError == "null";
    duplicateAcmeOwnerRefused = refused "mrjamVpsRenewal: another ACME" duplicatedAcme;
  };
  # Exercise the actual wrapper against an invented account and certificate.
  # A fake ACME executable refuses every verb except renew and records entry;
  # there is no network, real credential or ACME account in this test.
  renewalRuntime = pkgs.runCommand "mrjam-retained-acme-wrapper-synthetic" {
    nativeBuildInputs = [ pkgs.bash pkgs.coreutils pkgs.findutils pkgs.util-linux pkgs.openssl pkgs.python3 ];
    wrapper = lib.replaceStrings [ "/run/mrjam-acme/renew.lock" ] [ "./renew.lock" ] renewal.script;
    passAsFile = [ "wrapper" ];
  } ''
    mkdir -p test-bin
    cat > test-bin/lego <<'SH'
    #!${pkgs.bash}/bin/bash
    set -eu
    test "$LEGO_EMAIL" = synthetic@example.invalid
    test "$*" = '--accept-tos --path . --server https://acme.example.invalid/directory --key-type ec256 --http --http.webroot /var/lib/synthetic-acme --domains vision.mrj.am renew --no-random-sleep --dynamic'
    touch lego-called
    SH
    chmod +x test-bin/lego
    export PATH="$PWD/test-bin:$PATH"
    bash -n "$wrapperPath"
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
      -subj /CN=vision.mrj.am -addext subjectAltName=DNS:vision.mrj.am \
      -keyout certificate.key -out certificate.crt -days 1 >/dev/null 2>&1
    python - "$wrapperPath" <<'PY'
    import os, pathlib, shutil, subprocess, sys
    root = pathlib.Path.cwd()
    wrapper = pathlib.Path(sys.argv[1])
    def fixture(name):
        case = root / name
        keydir = case / "accounts/acme.example.invalid/synthetic@example.invalid/keys"
        keydir.mkdir(parents=True)
        (keydir / "synthetic@example.invalid.key").write_text("synthetic-account-key")
        (keydir.parent / "account.json").write_text('{"registration":{"body":{"status":"valid"}}}')
        certs = case / "certificates"
        certs.mkdir()
        for suffix, source in (("key", "certificate.key"), ("crt", "certificate.crt"), ("issuer.crt", "certificate.crt")):
            shutil.copyfile(root / source, certs / ("vision.mrj.am." + suffix))
        (certs / "vision.mrj.am.json").write_text("{}")
        (case / "out").mkdir()
        return case, keydir
    good, _ = fixture("valid-existing")
    subprocess.run(["bash", str(wrapper)], cwd=good, check=True)
    assert (good / "lego-called").is_file()
    assert (good / "out/fullchain.pem").read_bytes() == (root / "certificate.crt").read_bytes()
    assert (good / "out/key.pem").stat().st_mode & 0o777 == 0o640
    (good / "out/mrjam-renewed").unlink()
    subprocess.run(["bash", str(wrapper)], cwd=good, check=True)
    assert not (good / "out/mrjam-renewed").exists()
    for name in ("missing-account", "ambiguous-account", "missing-registration", "wrong-server", "symlink-key", "missing-certificate"):
        case, keys = fixture(name)
        if name == "missing-account":
            (keys / "synthetic@example.invalid.key").unlink()
        elif name == "ambiguous-account":
            (keys / "other.key").write_text("synthetic-only")
        elif name == "missing-registration":
            (keys.parent / "account.json").unlink()
        elif name == "wrong-server":
            (case / "accounts/acme.example.invalid").rename(case / "accounts/wrong.example.invalid")
        elif name == "symlink-key":
            key = keys / "synthetic@example.invalid.key"
            key.unlink()
            key.symlink_to(root / "certificate.key")
        else:
            (case / "certificates/vision.mrj.am.crt").unlink()
        result = subprocess.run(["bash", str(wrapper)], cwd=case)
        assert result.returncode != 0, name
        assert not (case / "lego-called").exists(), name
        assert not list((case / "out").iterdir()), name
    print("8 synthetic renewal-wrapper groups passed; no network or ACME issuance")
    PY
    touch "$out"
  '';
in assert lib.all (value: value) (builtins.attrValues result);
if output == "renewalRuntime" then renewalRuntime else result
