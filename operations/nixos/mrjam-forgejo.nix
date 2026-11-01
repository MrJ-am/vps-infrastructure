{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamForgejo;
in {
  options.services.mrjamForgejo = {
    enable = lib.mkEnableOption "future adoption Forgejo, blocked in this preparation";
    runner.enable = lib.mkEnableOption "future isolated runner, blocked in this preparation";
    preparation = lib.mkOption {
      type = lib.types.package;
      readOnly = true;
      default = import ../forgejo/locked-preparation.nix {
        system = pkgs.stdenv.hostPlatform.system;
      };
      description = ''
        Reviewable settings and static assets only. Installing this output does
        not install a service, create a database, register a runner or authorize
        migration. No secret is read while evaluating or building it. This
        package uses the explicitly locked candidate toolchain, independently
        of the host's package set; it does not replace the host's nixpkgs.
      '';
    };
  };

  # A code gate, deliberately not a candidate-controlled "approved" boolean.
  # The installed version, SSO adoption, migrations, backup/restore and runner
  # isolation are still unqualified. Replacing this gate needs a reviewed code
  # change and the separate release authorization described in ../release/.
  config.assertions = [
    {
      assertion = !cfg.enable;
      message = "mrjamForgejo: activation blocked; installed build, SSO, schema migration and restore compatibility are not qualified.";
    }
    {
      assertion = !cfg.runner.enable;
      message = "mrjamForgejo: runner activation blocked; no isolated executor is qualified, and none may be added to the VPS by this module.";
    }
  ];
}
