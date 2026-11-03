{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamValidationCoordinatorAttestation;
  authority = config.services.mrjamValidationAuthority;
  runner = config.services.mrjamForgejoRunner;
  package = import ./runner.nix { inherit pkgs; authorityPackage = authority.package; };
  closure = pkgs.closureInfo { rootPaths = [ package authority.package ]; };
  root = pkgs.runCommand "mrjam-forgejo-coordinator-authority-root-1" {} ''
    mkdir -p "$out"
    cp -a --reflink=auto ${runner.coordinatorRoot}/. "$out/"
    chmod u+w "$out" "$out/nix" "$out/nix/store" "$out/run"
    while IFS= read -r path; do
      if [ ! -e "$out$path" ]; then cp -a --reflink=auto "$path" "$out/nix/store/"; fi
    done < ${closure}/store-paths
    mkdir -p "$out/run/mrjam-validation-authority"
    touch "$out/run/mrjam-validation-authority/request.sock"
  '';
in {
  options.services.mrjamValidationCoordinatorAttestation = {
    enable = lib.mkEnableOption "bounded collector-to-content-authority coordinator variant";
    package = lib.mkOption { type = lib.types.package; readOnly = true; default = package; };
    root = lib.mkOption { type = lib.types.package; readOnly = true; default = root; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = runner.enable && authority.enable;
        message = "The attestation coordinator requires the isolated runner and its separately configured content authority."; }
      { assertion = pkgs.forgejo-runner.version == "13.2.0";
        message = "The attestation coordinator must use the same pinned runner toolchain."; }
    ];
    systemd.services.mrjam-forgejo-runner = {
      after = [ "mrjam-validation-authority.socket" ];
      requires = [ "mrjam-validation-authority.socket" ];
      serviceConfig = {
        ExecStart = lib.mkForce "${package}/bin/forgejo-runner daemon --config %d/runner-config";
        RootDirectory = lib.mkForce root;
        BindReadOnlyPaths = [ "/run/mrjam-validation-authority/request.sock" ];
      };
    };
  };
}
