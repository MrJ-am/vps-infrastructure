let
  base = import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; modules = [ ./vision-bascule-base-ancienne.nix ];
  };
  p = import ../scripts/vision-bascule-composants.nix {
    configuration = toString ./vision-bascule-base-ancienne.nix;
    source = toString ../vendor/vision/source;
    fournisseur = builtins.toFile "vision-fournisseur-ancien-test" "qualification";
  };
in assert !(base.options.infrastructure ? identite);
assert !(base.options.infrastructure ? admission);
assert !(base.options.infrastructure ? courriel);
assert p.resume.modules_passerelle_actualises;
assert p.resume.module_postgresql_actualise;
assert p.resume.garde_activation && !p.resume.generation_constructible;
assert p.lot.drvPath != "";
{ ancien_sans_identite_qualifie = true; garde_activation_ferme = true; }
