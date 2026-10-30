{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamInventory;
  account = "mrjam-inventory";
  root = "/var/lib/mrjam-inventory-access";
  # IDs are required before enablement; null never selects a new allocation.
  uid = if cfg.adoption.uid == null then 0 else cfg.adoption.uid;
  gid = if cfg.adoption.gid == null then 0 else cfg.adoption.gid;
  package = pkgs.callPackage ../inventory/package.nix {
    inherit uid gid;
    inherit (cfg) publicKeys;
  };
  authorizedKeys = lib.concatMapStrings (key: ''restrict,command="mrjam-inventory-v1" ${key}
'') cfg.publicKeys;
in {
  options.services.mrjamInventory = {
    enable = lib.mkEnableOption "adoption déclarative de l'accès d'inventaire borné existant";
    adoption.uid = lib.mkOption {
      type = lib.types.nullOr lib.types.ints.positive;
      default = null;
      description = "UID existant établi par le précontrôle borné ; aucune allocation implicite.";
    };
    adoption.gid = lib.mkOption {
      type = lib.types.nullOr lib.types.ints.positive;
      default = null;
      description = "GID existant établi par le précontrôle borné ; aucune allocation implicite.";
    };
    publicKeys = lib.mkOption {
      type = lib.types.listOf (lib.types.strMatching "ssh-ed25519 [A-Za-z0-9+/=]+( [A-Za-z0-9._@+-]+)?");
      default = [ ];
      description = "Clés publiques dédiées déjà approuvées ; jamais une clé privée ni une autorité CA.";
    };
    package = lib.mkOption {
      type = lib.types.package;
      readOnly = true;
      default = package;
      description = "Paquet et interpréteurs issus du nixpkgs verrouillé de l'assembleur.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = cfg.adoption.uid != null && cfg.adoption.gid != null;
        message = "mrjamInventory requires observed existing UID/GID; no invented or automatic IDs."; }
      { assertion = cfg.publicKeys != [ ] && lib.length cfg.publicKeys <= 4 && lib.length (lib.unique cfg.publicKeys) == lib.length cfg.publicKeys;
        message = "mrjamInventory requires unique approved public keys."; }
      { assertion = config.services.openssh.enable;
        message = "mrjamInventory requires the existing SSH service; it does not enable it implicitly."; }
      { assertion = config.users.users.${account}.extraGroups == [ ];
        message = "mrjamInventory refuses supplementary groups."; }
      { assertion = config.users.groups.${account}.members == [ ];
        message = "mrjamInventory group must not delegate the runtime lock to other members."; }
    ];
    users.groups.${account}.gid = gid;
    users.users.${account} = {
      inherit uid;
      isSystemUser = true;
      group = account;
      extraGroups = [ ];
      home = "${root}/home";
      createHome = false;
      hashedPassword = "!";
      shell = "${package}/bin/mrjam-inventory-login";
    };
    environment.etc."ssh/mrjam-inventory-authorized-keys" = {
      text = authorizedKeys;
      mode = "0444";
      user = "root";
      group = "root";
    };
    # OpenSSH accepts this directive globally only. The declaration must agree
    # with the authoritative host policy; a conflicting value is an eval error.
    services.openssh.settings.PermitUserEnvironment = false;
    services.openssh.extraConfig = lib.mkBefore ''
      Match User mrjam-inventory
        AuthenticationMethods publickey
        PubkeyAuthentication yes
        PasswordAuthentication no
        KbdInteractiveAuthentication no
        PermitEmptyPasswords no
        GSSAPIAuthentication no
        HostbasedAuthentication no
        AuthorizedKeysFile /etc/ssh/mrjam-inventory-authorized-keys
        AuthorizedKeysCommand none
        AuthorizedPrincipalsFile none
        AuthorizedPrincipalsCommand none
        TrustedUserCAKeys none
        ForceCommand mrjam-inventory-v1
        ChrootDirectory none
        DisableForwarding yes
        AllowAgentForwarding no
        AllowTcpForwarding no
        AllowStreamLocalForwarding no
        PermitOpen none
        PermitListen none
        PermitTunnel no
        PermitTTY no
        PermitUserRC no
        X11Forwarding no
        MaxSessions 1
      Match all
    '';
    # Existing legacy work is preserved. The new runner writes no jobs/reports:
    # retention is zero; no recursive chown, expiry or deletion of old files.
    systemd.tmpfiles.rules = [
      "d ${root} 0755 root root -"
      "d ${root}/home 0755 root root -"
      "d ${root}/home/.ssh 0755 root root -"
      "d ${root}/work 0700 ${account} ${account} -"
      "d /run/mrjam-inventory-lock 0750 root ${account} -"
      "f /run/mrjam-inventory-lock/operation.lock 0440 root ${account} -"
    ];
  };
}
