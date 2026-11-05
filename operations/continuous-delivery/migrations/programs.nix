# Named, tested programs for long-running/vendor/incompatible migrations.
# Each package must provide bin/{check,apply,verify,recover}. check runs only on
# synthetic fixtures in the Nix sandbox; apply/recover run during deployment.
{ pkgs, source }:
{ }
