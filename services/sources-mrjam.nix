{ pkgs }:
let
  noms = [ "mrj-auth" "vision-gestion" "vision-cycle" "mrjam-admission"
    "mrjam-fermeture" "mrjam-courriel" "keycloak-mrjam" ];
  code = nom: builtins.path {
    path = ./. + "/${nom}";
    name = "source-${nom}";
    filter = path: type:
      let nomFichier = baseNameOf path; in
      !(pkgs.lib.hasPrefix "." nomFichier) && nomFichier != "__pycache__" &&
      (type == "directory" || (type == "regular" &&
        (builtins.match ".*\\.(py|java|css|html|js|ftl|properties|nix|sh)$" nomFichier != null ||
          pkgs.lib.hasInfix "/META-INF/services/" path)));
  };
  installer = [ "identite-preparer.py" "identite-fermeture-configurer.py"
    "identite-amorcage-demarrer.sh" "identite-amorcage-postgresql.sh" ];
  modules = [ "identite.nix" "mrj-auth.nix" "vision-gestion.nix" "courriel.nix"
    "vision-cycle.nix" "admission.nix" "fermeture.nix" "identite-amorcage.nix" ];
in pkgs.runCommand "sources-services-mrjam" {} ''
  mkdir -p code/services code/scripts code/modules code/lib code/operations/identite "$out"
  ${pkgs.lib.concatMapStringsSep "\n" (nom: "cp -R ${code nom} code/services/${nom}") noms}
  ${pkgs.lib.concatMapStringsSep "\n" (nom: "cp ${../scripts + "/${nom}"} code/scripts/${nom}") installer}
  ${pkgs.lib.concatMapStringsSep "\n" (nom: "cp ${../modules + "/${nom}"} code/modules/${nom}") modules}
  cp ${../operations/identite/realm.json} code/operations/identite/realm.json
  cp ${../operations/identite/profil.json} code/operations/identite/profil.json
  cp ${../lib/keycloak-optimise.nix} code/lib/keycloak-optimise.nix
  cp ${../licenses/AGPL-3.0.txt} code/LICENSE
  cp ${../licenses/SERVICES-MRJAM.md} code/NOTICE.md
  chmod -R u+w code
  tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -czf "$out/services-mrjam.tar.gz" -C code .
''
