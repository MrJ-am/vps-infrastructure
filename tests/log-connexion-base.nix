{ pkgs, ... }:
{
  imports = [ ./log-evaluation-base.nix ];
  # Reproduire la génération Native antérieure au correctif, sans l'activer.
  disabledModules = [ ../modules/log-referrer.nix ];
  infrastructure.log = {
    enable = true;
    paquet = import ../assemblage/kanidm/artefact.nix {
      inherit pkgs;
      artefact = "/nix/store/0aqnq3k20yq30hf0bch64ghy3nj9bd66-kanidm-1.11.2";
    };
  };
}
