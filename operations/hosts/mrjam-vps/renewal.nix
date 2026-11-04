# Preserve existing ACME accounts without placing their contact in the Nix store.
# This is an explicit renewal-only adapter, not certificate/account bootstrap.
{ config, lib, pkgs, ... }:
let
  cfg = config.mrjamVpsRenewal;
  domain = lib.types.strMatching "[a-z0-9][a-z0-9.-]*[a-z0-9]";
  hash = lib.types.strMatching "[a-f0-9]{20}";
  certType = lib.types.submodule {
    options = {
      domain = lib.mkOption { type = domain; };
      extraDomains = lib.mkOption { type = lib.types.listOf domain; default = [ ]; };
      accountHash = lib.mkOption { type = hash; description = "Observed existing NixOS ACME account-directory hash; never computed from a private contact."; };
      certificateHash = lib.mkOption { type = hash; description = "Observed existing NixOS lego certificate-directory hash."; };
      server = lib.mkOption { type = lib.types.strMatching "https://[A-Za-z0-9./:_-]+"; };
      keyType = lib.mkOption { type = lib.types.enum [ "ec256" "ec384" "rsa2048" "rsa3072" "rsa4096" "rsa8192" ]; };
      webroot = lib.mkOption { type = lib.types.strMatching "/var/lib/[A-Za-z0-9_./-]+"; };
      interval = lib.mkOption { type = lib.types.str; description = "Observed timer calendar."; };
      jitter = lib.mkOption { type = lib.types.str; description = "Observed timer randomized delay."; };
      reloadServices = lib.mkOption { type = lib.types.listOf (lib.types.enum [ "nginx.service" "kanidm.service" ]); default = [ "nginx.service" ]; };
    };
  };
  safePath = path: !(lib.hasInfix "//" path) && !(lib.hasSuffix "/" path)
    && lib.all (part: part != "." && part != "..") (lib.splitString "/" path);
  renew = name: cert:
    let
      account = "/var/lib/acme/.lego/accounts/${cert.accountHash}";
      certificates = "/var/lib/acme/.lego/${name}/${cert.certificateHash}";
      serverFolder = builtins.replaceStrings [ ":" ] [ "_" ] (builtins.elemAt (lib.splitString "/" cert.server) 2);
      common = lib.escapeShellArgs ([ "--accept-tos" "--path" "." "--server" cert.server
        "--key-type" cert.keyType "--http" "--http.webroot" cert.webroot ]
        ++ lib.concatMap (value: [ "--domains" value ]) ([ cert.domain ] ++ cert.extraDomains));
    in {
      description = "Renew existing ACME certificate ${name} with its retained account";
      after = [ "network-online.target" "nginx.service" "mrjam-acme-runtime.service" ];
      wants = [ "network-online.target" ];
      requires = [ "nginx.service" "mrjam-acme-runtime.service" ];
      restartIfChanged = false;
      stopIfChanged = false;
      path = [ pkgs.coreutils pkgs.findutils pkgs.util-linux pkgs.openssl pkgs.lego ];
      script = ''
        set -euo pipefail
        umask 0077
        # No contact, account key, registration or ACME output enters journald.
        exec >/dev/null 2>&1
        exec 9>/run/mrjam-acme/renew.lock
        flock -x 9
        test -d accounts
        test ! -L accounts
        test -d certificates
        test ! -L certificates
        test -d out
        test ! -L out
        # Select exactly one existing account. A missing/ambiguous account fails
        # before network access. Contact stays in this private process environment.
        mapfile -d "" account_keys < <(find -P accounts -type f -name '*.key' -print0)
        test "''${#account_keys[@]}" -eq 1
        account_key="''${account_keys[0]}"
        test -s "$account_key"
        test ! -L "$account_key"
        export LEGO_EMAIL="''${account_key##*/}"
        export LEGO_EMAIL="''${LEGO_EMAIL%.key}"
        test -n "$LEGO_EMAIL"
        case "$LEGO_EMAIL" in *$'\n'*|*$'\r'*|*'/'*) exit 1;; esac
        # Match lego's exact layout before it can look up a different identity.
        account_user="accounts/${serverFolder}/$LEGO_EMAIL"
        test "$account_key" = "$account_user/keys/$LEGO_EMAIL.key"
        for directory in accounts/${serverFolder} "$account_user" "$account_user/keys"; do
          test -d "$directory"
          test ! -L "$directory"
        done
        registration="$account_user/account.json"
        test -s "$registration"
        test ! -L "$registration"
        for extension in crt key json issuer.crt; do
          file="certificates/${cert.domain}.$extension"
          test -s "$file"
          test ! -L "$file"
        done
        # There is deliberately no lego run/register fallback and no self-signed
        # certificate path. Missing state cannot create a new account or cert.
        lego ${common} renew --no-random-sleep --dynamic
        openssl x509 -in 'certificates/${cert.domain}.crt' -noout -checkend 0
        ${lib.concatMapStringsSep "\n" (value: "openssl x509 -in 'certificates/${cert.domain}.crt' -noout -checkhost ${lib.escapeShellArg value}") ([ cert.domain ] ++ cert.extraDomains)}
        openssl x509 -in 'certificates/${cert.domain}.crt' -pubkey -noout > certificate-public.pem
        openssl pkey -in 'certificates/${cert.domain}.key' -pubout > key-public.pem
        cmp -s certificate-public.pem key-public.pem
        if ! cmp -s 'certificates/${cert.domain}.crt' out/fullchain.pem; then
          install -m 0640 'certificates/${cert.domain}.crt' out/fullchain.pem.next
          install -m 0640 'certificates/${cert.domain}.key' out/key.pem.next
          install -m 0640 'certificates/${cert.domain}.issuer.crt' out/chain.pem.next
          cat out/key.pem.next out/fullchain.pem.next > out/full.pem.next
          chmod 0640 out/full.pem.next
          mv -f out/key.pem.next out/key.pem
          mv -f out/chain.pem.next out/chain.pem
          mv -f out/fullchain.pem.next out/fullchain.pem
          mv -f out/full.pem.next out/full.pem
          ln -sfn fullchain.pem out/cert.pem
          touch out/mrjam-renewed
        fi
      '';
      serviceConfig = {
        Type = "oneshot";
        User = "acme"; Group = "nginx";
        WorkingDirectory = "/tmp";
        PrivateTmp = true;
        BindReadOnlyPaths = [ "${account}:/tmp/accounts" ];
        BindPaths = [ "${certificates}:/tmp/certificates" "/var/lib/acme/${name}:/tmp/out" ];
        ReadWritePaths = [ certificates "/var/lib/acme/${name}" cert.webroot "/run/mrjam-acme" ];
        ExecStartPost = "+${pkgs.writeShellScript "mrjam-acme-reload-${name}" ''
          set -eu
          if test -f /var/lib/acme/${name}/mrjam-renewed; then
            ${pkgs.systemd}/bin/systemctl --no-block try-reload-or-restart ${lib.escapeShellArgs cert.reloadServices}
            ${pkgs.coreutils}/bin/rm /var/lib/acme/${name}/mrjam-renewed
          fi
        ''}";
        UMask = "0077";
        StandardOutput = "null"; StandardError = "null";
        NoNewPrivileges = true; ProtectSystem = "strict"; ProtectHome = true;
        PrivateDevices = true; ProtectKernelTunables = true; ProtectKernelModules = true;
        ProtectKernelLogs = true; ProtectControlGroups = true; ProtectClock = true;
        ProtectHostname = true; ProtectProc = "invisible"; ProcSubset = "pid";
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
        RestrictNamespaces = true; RestrictRealtime = true; RestrictSUIDSGID = true;
        LockPersonality = true; MemoryDenyWriteExecute = true;
        CapabilityBoundingSet = ""; AmbientCapabilities = "";
        TimeoutStartSec = "30min"; TasksMax = 64; MemoryMax = "256M"; CPUQuota = "25%";
      };
      unitConfig = {
        AssertPathIsDirectory = [ account certificates "/var/lib/acme/${name}" cert.webroot ];
        AssertPathExists = [ "/var/lib/acme/${name}/fullchain.pem" "/var/lib/acme/${name}/key.pem" ];
      };
    };
in {
  options.mrjamVpsRenewal = {
    enable = lib.mkEnableOption "renewal of explicitly observed existing ACME accounts";
    timersEnabled = lib.mkEnableOption "explicitly promoted renewal timers";
    certificates = lib.mkOption { type = lib.types.attrsOf certType; default = { }; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = cfg.certificates != { }; message = "mrjamVpsRenewal: exact observed certificate metadata is required."; }
      { assertion = config.security.acme.certs == { }; message = "mrjamVpsRenewal: another ACME generator must not own the retained state."; }
      { assertion = config.services.nginx.enable; message = "mrjamVpsRenewal: the HTTP challenge requires the declared Nginx service."; }
      { assertion = lib.all (name: builtins.match "[a-z0-9][a-z0-9.-]*[a-z0-9]" name != null) (builtins.attrNames cfg.certificates);
        message = "mrjamVpsRenewal: certificate directory names must be literal DNS names."; }
      { assertion = lib.all (cert: safePath cert.webroot && cert.reloadServices != [ ]
          && builtins.length (lib.unique ([ cert.domain ] ++ cert.extraDomains)) == 1 + builtins.length cert.extraDomains)
          (builtins.attrValues cfg.certificates);
        message = "mrjamVpsRenewal: canonical existing HTTP webroots, exact unique domains and reload services are required."; }
    ];
    users.groups.acme.gid = 995;
    users.users.acme = { uid = 996; isSystemUser = true; group = "acme"; createHome = false; };
    systemd.services = lib.mapAttrs' (name: cert: lib.nameValuePair "mrjam-acme-renew-${name}" (renew name cert)) cfg.certificates // {
      mrjam-acme-runtime = {
        description = "Private serialization directory for retained ACME renewals";
        serviceConfig = { Type = "oneshot"; RemainAfterExit = true; User = "acme";
          RuntimeDirectory = "mrjam-acme"; RuntimeDirectoryMode = "0700"; ExecStart = "${pkgs.coreutils}/bin/true"; };
      };
    };
    systemd.timers = lib.mapAttrs' (name: cert: lib.nameValuePair "mrjam-acme-renew-${name}" {
      wantedBy = lib.optional cfg.timersEnabled "timers.target";
      timerConfig = { OnCalendar = cert.interval; RandomizedDelaySec = cert.jitter; Persistent = true;
        Unit = "mrjam-acme-renew-${name}.service"; };
    }) cfg.certificates;
    services.nginx.virtualHosts = lib.mapAttrs (name: cert: {
      locations."^~ /.well-known/acme-challenge/" = { root = cert.webroot; extraConfig = "auth_basic off; allow all;"; };
    }) cfg.certificates;
  };
}
