let
  evaluer = configuration: import ../scripts/vision-interface-config.nix { inherit configuration; };
  avant = evaluer (toString ./vision-sans-interface.nix);
  apres = evaluer (toString ../hosts/hostinger/vision-interface.nix);
in assert avant.invariant == apres.invariant;
{ invariantsConserves = true; }
