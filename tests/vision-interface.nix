let
  evaluer = configuration: import ../scripts/vision-interface-config.nix { inherit configuration; };
  avant = evaluer (toString ../hosts/hostinger/configuration.nix);
  apres = evaluer (toString ../hosts/hostinger/vision-interface.nix);
in assert avant.invariant == apres.invariant;
{ invariantsConserves = true; }
