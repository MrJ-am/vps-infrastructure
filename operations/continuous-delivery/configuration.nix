# Authoritative, versioned additions to the complete adopted NixOS host.
# Change service/package selections here (or import further modules here).
# Data migrations belong to migrations/plan.json and its tested programs.
{ lib, pkgs, ... }:
{
  services.nginx.package = lib.mkOverride (-20) pkgs.nginx;
  services.postgresql.package = lib.mkOverride (-20) pkgs.postgresql_17;
}
