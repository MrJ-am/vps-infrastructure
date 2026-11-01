{ config, lib, pkgs, ... }:
let
  cfg = config.services.visionEmbeddings;
  python = pkgs.python3.withPackages (ps: [ ps.sentence-transformers ]);
in {
  options.services.visionEmbeddings = {
    enable = lib.mkEnableOption "fournisseur CPU local d'embeddings pour Vision";
    source = lib.mkOption {
      type = lib.types.path;
      description = "Source Vision revue et épinglée contenant scripts/embeddings.py.";
    };
    modelSource = lib.mkOption {
      type = lib.types.path;
      default = import ./modele.nix { inherit pkgs; };
      description = "Snapshot complet et épinglé du modèle ; aucune récupération réseau au démarrage.";
    };
  };
  config = lib.mkIf cfg.enable {
    systemd.services.vision-embeddings = {
      description = "Embeddings multilingues locaux de Vision";
      wantedBy = [ "multi-user.target" ];
      before = [ "vision.service" ];
      environment = {
        HF_HUB_OFFLINE = "1";
        TRANSFORMERS_OFFLINE = "1";
        HF_HOME = "/var/cache/vision-embeddings";
        OMP_NUM_THREADS = "2";
        TOKENIZERS_PARALLELISM = "false";
      };
      serviceConfig = {
        ExecStart = "${python}/bin/python ${cfg.source}/scripts/embeddings.py --modele ${cfg.modelSource}";
        DynamicUser = true;
        CacheDirectory = "vision-embeddings";
        Restart = "on-failure";
        NoNewPrivileges = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        RestrictAddressFamilies = [ "AF_INET" ];
        IPAddressDeny = "any";
        IPAddressAllow = [ "127.0.0.0/8" ];
        MemoryMax = "2G";
        TasksMax = 64;
        UMask = "0077";
      };
    };
    systemd.services.vision.environment.VISION_CURL = "${pkgs.curl}/bin/curl";
    # Un lot est lancé explicitement par les Actions VPS ; il est relançable
    # et ne bloque ni la migration SQL ni le démarrage du fournisseur.
    systemd.services.vision-embeddings-backfill = {
      description = "Vectoriser un lot d'items Vision sans modifier leurs contenus";
      after = [ "vision-embeddings.service" "vision-migrate.service" ];
      requires = [ "vision-embeddings.service" "vision-migrate.service" ];
      environment = {
        PGHOST = "/run/postgresql";
        PGDATABASE = "vision";
        PGUSER = "vision";
        VISION_PSQL = "${config.services.postgresql.package}/bin/psql";
      };
      serviceConfig = {
        Type = "oneshot";
        User = "vision";
        Group = "vision";
        ExecStart = "${python}/bin/python ${cfg.source}/scripts/backfill_embeddings.py --limite 100";
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" ];
        IPAddressDeny = "any";
        IPAddressAllow = [ "127.0.0.0/8" ];
        UMask = "0077";
      };
    };
  };
}
