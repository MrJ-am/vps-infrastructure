# Evaluation only; execution of these exact units is qualified separately.
{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  eval = modules: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux"; inherit modules;
  }).config;
  adapter = ../nixos/mrjam-identity-deletion.nix;
  fixture = {
    mrjamVpsApplications.workers.replayIdentityProtocol = "kanidm-delete-socket";
    services.mrjamIdentityDeletion = {
      enable = true;
      artifactStorePath = "/nix/store/79ls7yx6mxh4sryiipdn7k75ls1rbii8-mrjam-identity-deletion-0.1.0";
      kanidmCaFile = "/nix/store/l0avd78x86jr5swpayvz8a6z9y5g15z3-ca.pem/ca.pem";
      kanidmCaSha256 = "0cd98d2dd7a71afe5e2e93673933f15254c5a41a9be4682f27ec582e72c52ce0";
    };
  };
  base = [ ../hosts/mrjam-vps/candidate.nix adapter fixture ];
  active = eval base;
  disabled = eval [ adapter ];
  failed = config: map (item: item.message) (builtins.filter (item: !item.assertion) config.assertions);
  mutant = extra: eval (base ++ [ extra ]);
  peer = mutant ({lib,...}: { mrjamVpsApplications.identities.mrjam-vision-replay.uid = lib.mkForce 949; });
  collision = mutant { users.users.invented-collision = { uid = 948; isSystemUser = true; group = "mrjam-vision-replay"; }; };
  mixed = mutant { services.mrjamVisionReplay.kanidmCredentialFile = "/var/lib/invented-token"; };
  missing = mutant ({lib,...}: { services.mrjamIdentityDeletion.enable = lib.mkForce false; });
  changedReference = mutant { services.mrjamIdentityDeletion.credentialFile = "/var/lib/invented-token"; };
  deletion = active.systemd.services.mrjam-identity-deletion.serviceConfig;
  replay = active.systemd.services.mrjam-vision-replay.serviceConfig;
  result = {
    disabledInert = !(disabled.systemd.services ? mrjam-identity-deletion)
      && !(disabled.users.users ? mrjam-identity-deletion);
    compositionAssertions = failed active == [ ];
    exactUnixIdentities = active.users.users.mrjam-identity-deletion.uid == 948
      && deletion.Group == "mrjam-vision-replay" && active.users.groups.mrjam-vision-replay.gid == 944;
    privateRuntime = deletion.RuntimeDirectory == "mrjam-identity-deletion"
      && deletion.RuntimeDirectoryMode == "0750"
      && replay.BindReadOnlyPaths == [ "/run/mrjam-identity-deletion" ];
    providerCredentialOnlyInAdapter = deletion.LoadCredential == [ "kanidm:/var/lib/mrjam-identite/kanidm-replay.token" ]
      && replay.LoadCredential == [ "admissions:/var/lib/mrjam-worker-credentials/v1/closure" ]
      && active.services.mrjamVisionReplay.kanidmCredentialFile == null
      && active.services.mrjamVisionReplay.kanidmCaFile == null
      && active.services.mrjamVisionReplay.kanidmCaSha256 == null;
    loopbackOnlyAndNoTcpListener = deletion.IPAddressDeny == "any" && deletion.IPAddressAllow == "127.0.0.1/32"
      && deletion.RestrictNetworkInterfaces == [ "lo" ] && deletion.SocketBindDeny == "any";
    replayAdmissionPurgePreserved = replay.RestrictAddressFamilies == [ "AF_UNIX" "AF_INET" ]
      && replay.IPAddressDeny == "any" && replay.IPAddressAllow == "localhost";
    noAutomaticStart = active.systemd.services.mrjam-identity-deletion.wantedBy == [ ]
      && builtins.elem "mrjam-identity-deletion.service" active.systemd.services.mrjam-vision-replay.requires;
    wrongPeerRefused = builtins.elem "mrjamIdentityDeletion: the only client must be the declared replay peer UID/GID 944 with the socket protocol." (failed peer);
    duplicateUidRefused = builtins.elem "mrjamIdentityDeletion: UID 948 is reserved for this adapter alone." (failed collision);
    providerCredentialInReplayRefused = builtins.elem "Vision replay socket mode must never receive a provider credential or CA configuration." (failed mixed);
    missingAdapterRefused = builtins.elem "Vision replay socket mode requires the separately declared bounded deletion adapter." (failed missing);
    changedProviderReferenceRefused = builtins.elem "mrjamIdentityDeletion: preserve the explicit private provider credential reference." (failed changedReference);
  };
in assert lib.all (value: value) (builtins.attrValues result); result
