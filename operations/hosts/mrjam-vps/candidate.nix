# Complete staged composition; historical machine.nix stays blocked separately.
# No worker, migration, public ingress or retained timer is started by this file.
{ config, lib, pkgs, ... }:
let
  observed = builtins.fromJSON (builtins.readFile ./observed-public-services.json);
  runtimes = import ./runtimes.nix { inherit pkgs; };
  workers = "/nix/store/kbqmlal53czby17lpdycp8x2bhfiw7an-mrjam-vision-kanidm-workers-0.1.0-native-20261101";
  replay = "/nix/store/cp5rsnp0iqyd4j1k815b40avhz5jgp6h-mrjam-vision-delete-replay-0.1.0";
  broker = "/nix/store/1n0p3fn7nfdbwvpkbqlnk7y13057mivk-mrjam-identity-0.1.0";
  ca = "/nix/store/l0avd78x86jr5swpayvz8a6z9y5g15z3-ca.pem/ca.pem";
  caSha256 = "0cd98d2dd7a71afe5e2e93673933f15254c5a41a9be4682f27ec582e72c52ce0";
  workerCredentials = "/var/lib/mrjam-worker-credentials/v1";
  identity = number: { uid = number; gid = number; };
  site = host: { inherit host; certificateName = host; };
in {
  imports = [ ./machine-profile.nix ./core-services.nix ./application-services.nix
    ./renewal.nix ./state-adoption.nix ./backups.nix ../../deployment/boot-guard.nix
    ../../deployment/database-adoption.nix ../../deployment/credential-adoption.nix
    ../../deployment/forgejo-bootstrap/module.nix
    ../../deployment/credentials/provisioning-unit.nix
    ../../nixos/mrjam-identity.nix ../../nixos/mrjam-identity-deletion.nix
    ../../nixos/mrjam-embeddings.nix ];

  assertions = [
    { assertion = observed.schema_version == 1 && observed.hostname == "srv1982677"
        && !observed.credentials_exported && !observed.production_mutation;
      message = "mrjamCandidate: only the closed public preflight facts select this host."; }
    { assertion = pkgs.lib.version == "26.05pre-git" || lib.versions.majorMinor pkgs.lib.version == "26.05";
      message = "mrjamCandidate: use the independently preserved 26.05 host toolchain."; }
    { assertion = config.services.mrjamIdentity.principalRegistration.uid == 947
        && config.users.users.mrjam-vision-admission.uid == 947;
      message = "mrjamCandidate: admission registration must bind its exact Unix peer."; }
  ];
  # Received machine bytes remain intact; this public value was compared by the
  # closed preflight instead of assuming the old source hostname was installed.
  networking.hostName = lib.mkForce observed.hostname;
  # Received cff7b940/ac739eed Forgejo modules, without an overriding
  # declaration in the reviewed source closure. Retain SQL per-account quotas.
  services.mrjamForgejoHost.retainedQuotas = { maxRepositories = -1; totalStorage = "-1"; };

  mrjamVpsApplications = {
    enable = true;
    activeSlot = "blue";
    slots = lib.mapAttrs (_: value: builtins.unsafeDiscardStringContext (toString value)) runtimes;
    identities = {
      mrjam-rust-blue = identity 941;
      mrjam-rust-green = identity 942;
      mrjam-vision-archive = identity 943;
      mrjam-vision-replay = identity 944;
      mrjam-vision-cycle = identity 945;
      mrjam-vision-closure = identity 946;
      mrjam-vision-admission = identity 947;
    };
    sites = {
      audition = site "audition.mrj.am";
      log = site "log.mrj.am";
      logique = site "logique.echos.systems";
      mateval = site "principiipetit.io";
      vision = site "vision.mrj.am";
    };
    principiiRoot = null;
    databaseAccess = {
      mateval = { database = "matheval"; role = "matheval_app"; };
      matevalAdministration = { database = "matheval"; role = "matheval_admin"; };
      vision = { database = "vision"; role = "vision"; };
      visionAdministration = { database = "vision"; role = "vision_administration"; };
      visionJournal = { database = "vision_journal"; role = "vision_journal_writer"; };
      audition = { database = "vision"; role = "audition_app"; };
    };
    admissionApprovalCredentialFile = "${workerCredentials}/approval";
    workers = {
      enable = true;
      identityProtocol = "kanidm-native";
      replayIdentityProtocol = "kanidm-delete-socket";
      artifacts = lib.genAttrs [ "archive" "cycle" "closure" "admission" ] (_: workers) // { inherit replay; };
      kanidmCaFile = ca;
      kanidmCaSha256 = caSha256;
      visionDatabase = "vision";
      journalDatabase = "vision_journal";
      ageRecipient = null;
      archiveConfigurationCredentialFile = "${workerCredentials}/archive.json";
      archiveInitializeConfigurationCredentialFile = "${workerCredentials}/archive-initialize.json";
      credentials = {
        smtp = "${workerCredentials}/smtp.json";
        archiveRecipient = "${workerCredentials}/recipient";
        closure = "${workerCredentials}/closure";
        approval = "${workerCredentials}/approval";
        admissionIdentity = "/var/lib/mrjam-identite/kanidm-admission.token";
        cycleIdentity = "/var/lib/mrjam-identite/kanidm-cycle.token";
        replayIdentity = "/var/lib/mrjam-identite/kanidm-replay.token";
      };
    };
  };

  services.mrjamIdentity = {
    enable = true;
    artifactStorePath = broker;
    uid = 984;
    gid = 984;
    readersGid = 940;
    principalRegistration = { uid = 947; gid = 947; };
  };
  services.mrjamIdentityDeletion = {
    enable = true;
    artifactStorePath = "/nix/store/vxq44jamqwldh4q9j3xv50znz42lqg27-mrjam-identity-deletion-0.1.0-transport2";
    kanidmCaFile = ca;
    kanidmCaSha256 = caSha256;
  };
  services.mrjamKanidmWorkerProvision = {
    enable = true;
    package = builtins.storePath "/nix/store/5yqv8fsy6qhw45qs53qnirib9vl3cjhq-mrjam-kanidm-worker-provision-2";
  };
  services.mrjamEmbeddings = {
    enable = true;
    pythonStorePath = "/nix/store/dbnsh65c9fir9psk7waq3swb3mdh18cr-python3-3.13.15-env";
    modelStorePath = "/nix/store/mwwjyy4vlrwp59a7srjy53x24viksa6z-vision-modele-multilingue-e8f8c211226b";
  };
  mrjamVpsRenewal = {
    enable = true;
    certificates = observed.certificates;
  };
  mrjamVpsBackups.enable = true;

  # Installing the staged units does not select a public writer target. The
  # cutover backend starts private prerequisites explicitly after adoption.
  systemd.targets.postgresql.wantedBy = lib.mkForce [ ];
  systemd.services.nginx.wantedBy = lib.mkForce [ ];
  systemd.services.mrjam-vision-admission = {
    after = [ "mrjam-identity.service" ];
    requires = [ "mrjam-identity.service" ];
  };
  systemd.services.vision-embeddings.stopIfChanged = false;
}
