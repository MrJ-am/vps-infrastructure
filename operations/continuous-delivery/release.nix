{ source, revision, previousServer ? null, pkgs ? import ../forgejo/locked-toolchain.nix { } }:
let
  server = import ./server.nix { inherit source revision pkgs; };
  components = import ./components/default.nix { inherit source revision pkgs; };
  host = import ./full-host.nix {
    inherit source revision server;
    inherit (components) frontends vise;
  };
  declared = builtins.fromJSON (builtins.readFile ./migrations/plan.json);
  programs = import ./migrations/programs.nix { inherit pkgs source; };
  plan = declared // { steps = map (step:
    if step.driver == "program" then builtins.removeAttrs step [ "program" ] // {
      package = toString programs.${step.program};
    } else step) declared.steps; };
  migrations = pkgs.runCommand "mrjam-migrations-${builtins.substring 0 12 revision}" { } ''
    mkdir -p "$out"
    cp -R ${./migrations}/. "$out/"
    chmod -R u+w "$out"
    cp ${pkgs.writeText "migration-plan.json" (builtins.toJSON plan)} "$out/plan.json"
  '';
  checks = import ./tests.nix {
    inherit source pkgs server previousServer;
    runtime = host.runtimes.blue;
    migrationPlan = "${migrations}/plan.json";
    postgres = host.postgresql;
  };
  cfg = host.configuration;
  controls = import ./services.nix { inherit pkgs; };
  manifest = {
    format = 2;
    inherit revision;
    system = toString host.system;
    engine = toString host.engine;
    inherit controls;
    server = toString server;
    frontends = toString components.frontends;
    vise = toString components.vise;
    runtimes = builtins.mapAttrs (_: value: toString value) host.runtimes;
    nginx_template = toString host.nginxTemplate;
    nginx = toString host.nginx;
    postgresql = toString host.postgresql;
    postgresql_data = host.postgresqlData;
    stateful_versions = {
      postgresql = cfg.services.postgresql.package.version;
      forgejo = pkgs.lib.getVersion cfg.services.mrjamForgejoHost.artifactStorePath;
      kanidm = pkgs.lib.getVersion cfg.services.mrjamKanidmHost.artifactStorePath;
      nextcloud = cfg.services.nextcloud.package.version;
    };
    managed_units = [ "postgresql" "kanidm" "mrjam-identity" "mrjam-identity-deletion"
      "mrjam-identity-aliases" "forgejo" "phpfpm-nextcloud" "redis-nextcloud" "vise" "nginx" ];
  };
in pkgs.runCommand "mrjam-vps-release-${builtins.substring 0 12 revision}" { } ''
  test -e ${checks}
  mkdir -p "$out/share/mrjam"
  ln -s ${server}/bin "$out/bin"
  ln -s ${migrations} "$out/migrations"
  cp ${pkgs.writeText "mrjam-release.json" (builtins.toJSON manifest)} "$out/release.json"
  printf '%s\n' '${revision}' > "$out/share/mrjam/source-revision"
''
