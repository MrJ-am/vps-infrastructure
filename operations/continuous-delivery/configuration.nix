# Authoritative, versioned additions to the complete adopted NixOS host.
# Change service/package selections here (or import further modules here).
# Data migrations belong to migrations/plan.json and its tested programs.
{ lib, pkgs, ... }:
{
  services.nginx.package = lib.mkOverride (-20) pkgs.nginx;
  services.nginx.virtualHosts."vision.mrj.am".extraConfig = lib.mkAfter ''
    add_header X-Mrjam-Delivery-Proof "codex-cloud-20261105" always;
  '';
  services.postgresql.package = lib.mkOverride (-20) pkgs.postgresql_17;
}
