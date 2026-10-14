{ site, paquetMetier }:
{ lib, ... }: {
  infrastructure.metier.paquet = lib.mkOverride 10 paquetMetier;
  infrastructure.metier.documentVision = lib.mkOverride 10 (toString site);
}
