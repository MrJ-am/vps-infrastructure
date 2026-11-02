# Evaluate the full candidate; the historical incomplete wrapper stays blocked.
{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  eval = modules: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    inherit modules;
  }).config;
  staged = eval [ ../hosts/mrjam-vps/candidate.nix ];
  promoted = eval [ ../hosts/mrjam-vps/candidate-promoted.nix ];
  preparation = eval [ ../hosts/mrjam-vps/machine.nix ];
  failures = config: map (item: item.message) (builtins.filter (item: !item.assertion) config.assertions);
  gate = "mrjamVpsMachine: complete host activation blocked. Service composition, installed-state adoption, backup/restore and cutover are not qualified. This gate requires a reviewed code change, not an approval flag.";
  workerNames = [ "archive" "replay" "cycle" "closure" "admission" ];
  workerUnits = map (name: "mrjam-vision-${name}") workerNames;
  adoptionUnits = [ "mrjam-admission-native-adopt" "mrjam-cycle-mail-adopt" "mrjam-archive-mail-adopt" ];
  explicitUnits = [ "mrjam-worker-credentials-adapt" "mrjam-adopt-matheval" "mrjam-bootstrap-journal"
    "mrjam-adopt-forgejo-role" "mrjam-upgrade-forgejo-schema" "mrjam-forgejo-probe" "mrjam-forgejo-bootstrap"
    "mrjam-kanidm-worker-provision" ];
  inactive = config: units: lib.all (name: config.systemd.services.${name}.wantedBy == [ ]) units;
  publicHosts = [ "audition.mrj.am" "cloud.mrj.am" "forge.mrj.am" "log.mrj.am"
    "logique.echos.systems" "principiipetit.io" "vision.mrj.am" "www.principiipetit.io" ];
  lock = (builtins.fromJSON (builtins.readFile ../hosts/mrjam-vps/application-artifacts.json)).outputs;
  roots = map (value: builtins.unsafeDiscardStringContext (toString value)) staged.system.extraDependencies;
  missingPrivate = eval [ ../hosts/mrjam-vps/candidate.nix ({lib,...}: {
    mrjamVpsApplications.workers.archiveInitializeConfigurationCredentialFile = lib.mkForce null;
  }) ];
  mixedArchive = eval [ ../hosts/mrjam-vps/candidate.nix ({lib,...}: {
    mrjamVpsApplications.workers.ageRecipient = lib.mkForce "age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq";
  }) ];
  oldArchive = eval [ ../hosts/mrjam-vps/candidate.nix ({lib,...}: {
    mrjamVpsApplications.workers.artifacts.archive = lib.mkForce lock.vision_archive.store_path;
  }) ];
  result = {
    stagedCompositionAssertions = failures staged == [ ];
    promotedCompositionAssertions = failures promoted == [ ];
    incompletePreparationStillBlocked = builtins.elem gate (failures preparation);
    observedHostname = staged.networking.hostName == "srv1982677";
    machineStateVersionRetained = staged.system.stateVersion ==
      (builtins.fromJSON (builtins.readFile ../hosts/mrjam-vps/received-profile.json)).state_version;
    eightObservedHostsOnly = builtins.attrNames staged.services.nginx.virtualHosts == publicHosts;
    noViseUnit = !(staged.systemd.services ? vise) && !(staged.services.nginx.virtualHosts ? "vise.mrj.am");
    noInventedStyleOrLogoDomain = !(staged.services.nginx.virtualHosts ? "style.mrj.am")
      && !(staged.services.nginx.virtualHosts ? "logo.mrj.am");
    sevenFrontendClosuresRetained = lib.all (name: builtins.elem lock."frontend_${name}".store_path roots)
      [ "audition" "log" "logique" "logo" "mateval" "style" "vision" ];
    unchangedServerRetained = staged.services.mrjamRust.slots.blue.artifactStorePath == lock.server.store_path;
    bothQualifiedRuntimes = staged.services.mrjamRust.slots.blue.runtimeConfigStorePath == "/nix/store/i6sihwyslybsjf3qxx8k6pqb18n0wcak-mrjam-runtime-blue"
      && staged.services.mrjamRust.slots.green.runtimeConfigStorePath == "/nix/store/qp7jys8wcvyc2w611y6acl206n5yq2vg-mrjam-runtime-green";
    fourNativeWorkersUnchanged = lib.all (name: staged.mrjamVpsApplications.workers.artifacts.${name} ==
      "/nix/store/kbqmlal53czby17lpdycp8x2bhfiw7an-mrjam-vision-kanidm-workers-0.1.0-native-20261101")
      [ "archive" "cycle" "closure" "admission" ];
    replaySeparatelyBuilt = staged.services.mrjamVisionReplay.artifactStorePath ==
      "/nix/store/cp5rsnp0iqyd4j1k815b40avhz5jgp6h-mrjam-vision-delete-replay-0.1.0";
    nativeProtocolsSelected = staged.services.mrjamVisionAdmission.identityProtocol == "kanidm-native"
      && staged.services.mrjamVisionCycle.identityProtocol == "kanidm-native"
      && staged.services.mrjamVisionReplay.identityProtocol == "kanidm-delete-socket";
    deletionAdapterExact = staged.services.mrjamIdentityDeletion.artifactStorePath ==
      "/nix/store/vxq44jamqwldh4q9j3xv50znz42lqg27-mrjam-identity-deletion-0.1.0-transport2"
      && staged.users.users.mrjam-identity-deletion.uid == 948
      && staged.systemd.services.mrjam-identity-deletion.serviceConfig.Group == "mrjam-vision-replay";
    replayWithoutProviderCredential = staged.services.mrjamVisionReplay.kanidmCredentialFile == null
      && staged.services.mrjamVisionReplay.kanidmCaFile == null
      && staged.systemd.services.mrjam-vision-replay.serviceConfig.LoadCredential == [ "admissions:/var/lib/mrjam-worker-credentials/v1/closure" ]
      && staged.systemd.services.mrjam-identity-deletion.serviceConfig.LoadCredential == [ "kanidm:/var/lib/mrjam-identite/kanidm-replay.token" ];
    caExact = staged.services.mrjamVisionAdmission.kanidmCaFile == "/nix/store/l0avd78x86jr5swpayvz8a6z9y5g15z3-ca.pem/ca.pem"
      && staged.services.mrjamVisionAdmission.kanidmCaSha256 == "0cd98d2dd7a71afe5e2e93673933f15254c5a41a9be4682f27ec582e72c52ce0";
    distinctNativeTokenReferences = builtins.length (lib.unique (map (name: staged.mrjamVpsApplications.workers.credentials.${name})
      [ "admissionIdentity" "cycleIdentity" "replayIdentity" ])) == 3;
    aliasReadersSeparate = staged.users.groups.mrjam-log-readers.gid == 940
      && staged.services.mrjamIdentity.uid == 984 && staged.services.mrjamIdentity.gid == 984
      && staged.systemd.services.mrjam-identity.serviceConfig.Group == "mrjam-log-readers";
    admissionPeerExact = staged.services.mrjamIdentity.principalRegistration == { uid = 947; gid = 947; };
    fixedApplicationIdentities = map (name: staged.users.users.${name}.uid)
      ([ "mrjam-rust-blue" "mrjam-rust-green" ] ++ workerUnits) == [ 941 942 943 944 945 946 947 ];
    embeddingsExact = staged.services.mrjamEmbeddings.pythonStorePath == "/nix/store/dbnsh65c9fir9psk7waq3swb3mdh18cr-python3-3.13.15-env"
      && staged.services.mrjamEmbeddings.modelStorePath == "/nix/store/mwwjyy4vlrwp59a7srjy53x24viksa6z-vision-modele-multilingue-e8f8c211226b";
    postgresPeerAndNoBootstrap = staged.services.postgresql.settings.listen_addresses == ""
      && staged.services.postgresql.ensureDatabases == [ ] && staged.services.postgresql.ensureUsers == [ ]
      && staged.services.postgresql.initialScript == null;
    auditionKeepsExistingDatabase = staged.mrjamVpsApplications.databaseAccess.audition == { database = "vision"; role = "audition_app"; };
    noReplayedBusinessMigration = !lib.hasInfix "migrations/0" staged.systemd.services.postgresql.preStart;
    mathevalPrefixAndRootRedirect = staged.services.nginx.virtualHosts."principiipetit.io".locations."^~ /matheval/".proxyPass == "http://127.0.0.1:38101"
      && staged.services.nginx.virtualHosts."principiipetit.io".locations."= /".return == "308 /matheval/";
    wwwRedirect = staged.services.nginx.virtualHosts."www.principiipetit.io".locations."/".return == "308 https://principiipetit.io$request_uri";
    nativeAdminEndpointsPrivate = lib.all (path: staged.services.nginx.virtualHosts."log.mrj.am".locations."^~ ${path}".return == "404")
      [ "/v1/raw/" "/v1/oauth2/" "/v1/service_account/" "/scim/" ];
    archivePrivateConfigOnly = staged.services.mrjamVisionArchive.ageRecipient == null
      && lib.hasInfix "--config /run/credentials/mrjam-vision-archive.service/configuration" staged.systemd.services.mrjam-vision-archive.serviceConfig.ExecStart
      && builtins.elem "configuration:/var/lib/mrjam-worker-credentials/v1/archive.json" staged.systemd.services.mrjam-vision-archive.serviceConfig.LoadCredential;
    archiveInitializePrivateConfig = lib.hasInfix "--config /run/credentials/mrjam-vision-archive-initialize.service/configuration"
      staged.systemd.services.mrjam-vision-archive-initialize.serviceConfig.ExecStart;
    archiveMissingCompanionRefused = builtins.elem "Vision archive requires either both private configurations or one public age recipient." (failures missingPrivate);
    archiveMixedRecipientRefused = builtins.elem "Vision archive requires either both private configurations or one public age recipient." (failures mixedArchive);
    legacyArchiveNotPromotable = builtins.elem "mrjamVpsApplications: native identity requires all five adapted worker artifacts, including archival of both historical and native issuers." (failures oldArchive);
    adoptionNeverAutomatic = inactive staged adoptionUnits && inactive promoted adoptionUnits;
    mailAdoptionDdlWhitespaceV3 = lib.all (config:
      config.systemd.services.mrjam-cycle-mail-adopt.serviceConfig.ExecStart
        == "/nix/store/8x4pybgyhkz01jqd41363wfs5rz0fm8i-mrjam-mail-native-adoption-3/bin/mrjam-cycle-mail-adopt"
      && config.systemd.services.mrjam-archive-mail-adopt.serviceConfig.ExecStart
        == "/nix/store/8x4pybgyhkz01jqd41363wfs5rz0fm8i-mrjam-mail-native-adoption-3/bin/mrjam-archive-mail-adopt") [ staged promoted ];
    databaseAndCredentialAdoptionNeverAutomatic = inactive staged explicitUnits && inactive promoted explicitUnits;
    onlyExplicitDatabaseMigrationUnits = staged.systemd.services.mrjam-adopt-matheval.serviceConfig.User == "postgres"
      && staged.systemd.services.mrjam-bootstrap-journal.serviceConfig.User == "postgres"
      && staged.systemd.services.mrjam-adopt-forgejo-role.serviceConfig.User == "postgres"
      && staged.systemd.services.mrjam-upgrade-forgejo-schema.serviceConfig.User == "forgejo"
      && lib.all (name: staged.systemd.services.${name}.serviceConfig.PrivateNetwork)
        [ "mrjam-adopt-matheval" "mrjam-bootstrap-journal" "mrjam-adopt-forgejo-role" "mrjam-upgrade-forgejo-schema" ];
    privateCredentialAdaptationIsolated = staged.systemd.services.mrjam-worker-credentials-adapt.serviceConfig.PrivateNetwork
      && staged.systemd.services.mrjam-worker-credentials-adapt.serviceConfig.BindReadOnlyPaths == [ "/run/mrjam-worker-credential-adaptation" ]
      && staged.systemd.services.mrjam-worker-credentials-adapt.serviceConfig.ReadWritePaths == [ "/var/lib/mrjam-worker-credentials" ];
    humanCredentialProvisioningExactAndLoopbackOnly = let
      unit = staged.systemd.services.mrjam-kanidm-worker-provision.serviceConfig;
    in unit.ExecStart == "/nix/store/5yqv8fsy6qhw45qs53qnirib9vl3cjhq-mrjam-kanidm-worker-provision-2/bin/mrjam-kanidm-worker-provision"
      && unit.User == "root" && unit.IPAddressDeny == "any" && unit.IPAddressAllow == "127.0.0.1/32"
      && unit.RestrictNetworkInterfaces == [ "lo" ]
      && unit.LoadCredential == [ "identity-session:/run/mrjam-kanidm-worker-login/identity.json"
        "access-session:/run/mrjam-kanidm-worker-login/access.json" ];
    adoptionImagesReadOnly = map (name: staged.systemd.services.${name}.serviceConfig.BindReadOnlyPaths) adoptionUnits
      == [ [ "/run/mrjam-admission-adoption" ] [ "/run/mrjam-cycle-mail-adoption" ] [ "/run/mrjam-archive-mail-adoption" ] ];
    adoptionNoNetwork = lib.all (name: staged.systemd.services.${name}.serviceConfig.PrivateNetwork) adoptionUnits;
    stagedApplicationsNotStarted = inactive staged ([ "mrjam-rust-blue" "mrjam-rust-green" "mrjam-identity" "mrjam-identity-deletion"
      "forgejo" "kanidm" "phpfpm-nextcloud" "redis-nextcloud" "vision-embeddings" "nginx" ] ++ workerUnits)
      && staged.systemd.targets.postgresql.wantedBy == [ ];
    stagedTimersNotPromoted = !staged.mrjamVpsRenewal.timersEnabled
      && !staged.services.mrjamVisionArchive.timer.enable && !staged.services.mrjamVisionCycle.timer.enable
      && !staged.services.mrjamVisionReplay.timer.enable && !staged.services.mrjamVisionAdmission.admissionsOpen;
    promotedOnlyActiveSlot = promoted.systemd.services.mrjam-rust-blue.wantedBy == [ "multi-user.target" ]
      && promoted.systemd.services.mrjam-rust-green.wantedBy == [ ];
    promotedWritersExplicit = promoted.services.mrjamVisionAdmission.admissionsOpen
      && promoted.services.mrjamVisionArchive.timer.enable && promoted.services.mrjamVisionCycle.timer.enable
      && promoted.services.mrjamVisionReplay.timer.enable && promoted.services.mrjamIdentity.startAtBoot
      && promoted.services.mrjamIdentityDeletion.startAtBoot;
    renewalsKeepEightAccounts = builtins.attrNames staged.mrjamVpsRenewal.certificates == publicHosts
      && lib.all (cert: cert.accountHash == "a96772ab152e39f749f9" && cert.certificateHash == "748661661a99cbbf91d5"
        && cert.webroot == "/var/lib/acme/acme-challenge") (builtins.attrValues staged.mrjamVpsRenewal.certificates);
    kanidmCertificateReloadRetained = staged.mrjamVpsRenewal.certificates."log.mrj.am".reloadServices == [ "nginx.service" "kanidm.service" ];
    noAcmeBootstrap = staged.security.acme.certs == { };
    renewalPromotionExplicit = promoted.mrjamVpsRenewal.timersEnabled
      && lib.all (name: promoted.systemd.timers."mrjam-acme-renew-${name}".wantedBy == [ "timers.target" ]) publicHosts;
    phpContainmentPreserved = staged.systemd.services.phpfpm-nextcloud.unitConfig.ConditionPathExists == "!/var/lib/nextcloud-php-security/blocked";
    forgejoSsoConfigurationPreserved = let settings = staged.services.mrjamForgejoHost.settings; in
      !settings.service.ENABLE_INTERNAL_SIGNIN && !settings.service.ENABLE_BASIC_AUTHENTICATION
      && settings.service.ALLOW_ONLY_EXTERNAL_REGISTRATION && settings.oauth2_client.ENABLE_AUTO_REGISTRATION
      && settings.oauth2_client.ACCOUNT_LINKING == "disabled" && settings.oauth2_client.USERNAME == "nickname"
      && settings.oauth2_client.OPENID_CONNECT_SCOPES == "openid profile email"
      && !(staged.systemd.services ? forgejo-identity) && !(staged.systemd.services ? forgejo-account);
    forgejoRetainedSecretsOnly = staged.systemd.services.forgejo.environment.FORGEJO__SECURITY__SECRET_KEY__FILE == "/var/lib/forgejo/custom/conf/secret_key"
      && staged.systemd.services.forgejo.environment.FORGEJO__SECURITY__INTERNAL_TOKEN__FILE == "/var/lib/forgejo/custom/conf/internal_token"
      && staged.systemd.services.forgejo.environment.FORGEJO__OAUTH2__JWT_SECRET__FILE == "/var/lib/forgejo/custom/conf/oauth2_jwt_secret"
      && lib.hasInfix "--config /run/mrjam-forgejo/app.ini" staged.systemd.services.forgejo.serviceConfig.ExecStart;
    forgejoQuotaDefaultsPreserved = staged.services.mrjamForgejoHost.settings.quota.ENABLED
      && staged.services.mrjamForgejoHost.settings."quota.default".TOTAL == "-1"
      && staged.services.mrjamForgejoHost.settings.repository.MAX_CREATION_LIMIT == -1;
    forgejoTechnicalBootstrapBindsRetainedIdentity = staged.systemd.services.mrjam-forgejo-bootstrap.serviceConfig.ExecStart ==
      "/nix/store/8pkxq7pahlmhlmf6v890q2ica69cflsy-mrjam-forgejo-technical-bootstrap-1/bin/mrjam-forgejo-bootstrap";
    bootRecoveryGuardPresent = staged.systemd.generators ? mrjam-first-cutover-guard;
    portableRuntimeGuardExact = staged.systemd.generators.mrjam-first-cutover-guard ==
      "/nix/store/11gb9i2v7b3980zylx4pnr3wh7hd8djf-mrjam-first-cutover-boot-guard/bin/mrjam-first-cutover-guard"
      && promoted.systemd.generators.mrjam-first-cutover-guard == staged.systemd.generators.mrjam-first-cutover-guard;
    existingPostgresqlBackupSelection = staged.services.postgresqlBackup.databases == [ "matheval" "nextcloud" ]
      && staged.services.postgresqlBackup.location == "/var/backup/postgresql";
    backupTimersRequirePromotion = !staged.mrjamVpsBackups.promote && promoted.mrjamVpsBackups.promote
      && lib.all (name: staged.systemd.timers.${name}.wantedBy == [ ]
        && promoted.systemd.timers.${name}.wantedBy == [ "timers.target" ])
        [ "mrjam-sauvegarde" "forgejo-backup" "nextcloud-backup" "postgresqlBackup-matheval" "postgresqlBackup-nextcloud" ];
    nativeExportNeverAutostarts = staged.systemd.services.mrjam-kanidm-backup.wantedBy == [ ]
      && promoted.systemd.services.mrjam-kanidm-backup.wantedBy == [ ];
    nativeBackupCredentialSeparate = builtins.elem "archive-configuration:/var/lib/mrjam-worker-credentials/v1/archive.json"
      staged.systemd.services.mrjam-sauvegarde.serviceConfig.LoadCredential;
    backupDiagnosticsPrivate = lib.all (name: staged.systemd.services.${name}.serviceConfig.StandardOutput == "null"
      && staged.systemd.services.${name}.serviceConfig.StandardError == "null")
      [ "mrjam-sauvegarde" "mrjam-kanidm-backup" "forgejo-backup" "nextcloud-backup" ];
  };
in assert lib.all (value: value) (builtins.attrValues result); result
