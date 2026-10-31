{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../nixos/mrjam-validation-worker.nix {
      system.stateVersion = "26.05"; # Fixture only, not the installed VPS value.
      services.mrjamValidationWorker = {
        rulesRevision = "1111111111111111111111111111111111111111";
        validator = pkgs.writeShellScriptBin "mrjam-validate" "exit 2"; # No pretend-success rules.
      };
    } extra ];
  }).config;
  disabled = evaluate { };
  enabled = evaluate { services.mrjamValidationWorker.enable = true; };
  service = enabled.systemd.services."mrjam-validation-worker@".serviceConfig;
  socket = enabled.systemd.sockets.mrjam-validation-worker;
  account = enabled.users.users.mrjam-validation-worker;
  # Inspect JSON metadata without forcing/building derivations during evaluation;
  # the actual environment.etc text retains all Nix dependency contexts.
  policy = builtins.fromJSON (builtins.unsafeDiscardStringContext enabled.environment.etc."mrjam-validation-worker/policy.json".text);
  results = {
    disabledInert = !(disabled.systemd.services ? "mrjam-validation-worker@") && !(disabled.users.users ? mrjam-validation-worker);
    noAutomaticStart = socket.wantedBy == [ ];
    fixedLocalSocket = socket.listenStreams == [ "/run/mrjam-validation/request.sock" ] && socket.socketConfig.SocketMode == "0660";
    singleJob = socket.socketConfig.Accept && socket.socketConfig.MaxConnections == 1 && socket.socketConfig.Backlog == 1;
    automaticTemplateInstance = !(socket.socketConfig ? Service);
    noCallerMembersAssigned = enabled.users.groups.mrjam-validation-submitters.members == [ ];
    dedicatedUnprivilegedAccount = account.isSystemUser && account.extraGroups == [ ] && account.hashedPassword == "!" && !account.createHome;
    namespaceNetwork = service.PrivateNetwork && service.IPAddressDeny == "any" && service.IPAddressAllow == "localhost";
    credentialsInaccessible = builtins.elem "-/run/credentials" service.InaccessiblePaths && !(service ? LoadCredential);
    noDockerSocket = builtins.elem "-/var/run/docker.sock" service.InaccessiblePaths;
    noHostCapabilities = service.CapabilityBoundingSet == "" && service.NoNewPrivileges;
    composedPidBoundary = service.PrivatePIDs && service.ProcSubset == "all" && service.ProtectProc == "default" && service.CapabilityBoundingSet == "" && service.NoNewPrivileges;
    enforcedBudgets = service.MemoryMax == "2G" && service.CPUQuota == "100%" && service.TasksMax == 256 && service.RuntimeMaxSec == 1830;
    processTreeKill = service.KillMode == "control-group";
    exactIndependentRulesReference = policy.rules_revision == "1111111111111111111111111111111111111111" && lib.hasSuffix "-mrjam-validate" policy.validator_store;
    sourceOnlyRoot = service.ReadOnlyPaths == [ "/var/lib/mrjam-validation-input" ];
    protectedClosureCopy = enabled.environment.etc."mrjam-validation-worker/store-paths".mode == "0444"
      && enabled.environment.etc."mrjam-validation-worker/store-paths".uid == 0
      && builtins.unsafeDiscardStringContext enabled.environment.etc."mrjam-validation-worker/store-paths".source == policy.closure_file
      && map builtins.unsafeDiscardStringContext service.BindReadOnlyPaths == [ "/etc/mrjam-validation-worker/store-paths:${policy.closure_file}" ];
  };
in assert builtins.all (x: x) (builtins.attrValues results); results
