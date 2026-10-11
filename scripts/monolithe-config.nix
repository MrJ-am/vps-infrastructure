{ configuration, paquet, documentVision, ressourcesMatheval, bankVersion }:
(import ./monolithe-evaluation.nix {
  inherit configuration paquet documentVision ressourcesMatheval bankVersion;
}).rapport
