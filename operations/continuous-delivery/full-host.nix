{ source, revision, server, frontends, vise }:
let
  baseline = import ./installed-baseline.nix { };
  pkgs = import baseline.nixpkgs { system = "x86_64-linux"; };
  lib = pkgs.lib;
  engine = import ./package.nix { };
  units = import ./services.nix { };
  before = baseline.evaluate [ ];
  names = [ "log" "audition" "vision" "mateval" "logique" ];
  hosts = {
    "log.mrj.am" = "log";
    "audition.mrj.am" = "audition";
    "vision.mrj.am" = "vision";
    "principiipetit.io" = "mateval";
    "logique.echos.systems" = "logique";
  };
  runtime = slot: pkgs.runCommand "mrjam-runtime-${slot}-${builtins.substring 0 12 revision}" {
    nativeBuildInputs = [ pkgs.python3 ];
  } ''
    mkdir -p "$out"
    python3 - "$out/runtime.json" <<'PY'
    import hashlib,json,pathlib,sys
    runtime=json.loads(pathlib.Path('${./runtime-base.json}').read_text())
    host_names=json.loads('${builtins.toJSON hosts}')
    for asset in runtime['assets']:
        directory=pathlib.Path('${frontends}')/host_names[asset['host']]
        asset['directory']=str(directory)
        asset['payload_prefix']=""
        asset['manifest_sha256']=hashlib.sha256((directory/'artifact.json').read_bytes()).hexdigest()
    text=json.dumps(runtime).replace('/run/credentials/mrjam-rust-blue.service/',
                                    '/run/credentials/mrjam-rust-${slot}.service/')
    pathlib.Path(sys.argv[1]).write_text(text+'\n')
    PY
  '';
  runtimes = lib.genAttrs [ "blue" "green" ] runtime;
  legacy = [ "mrjam-forgejo-runner" "mrjam-github-discovery" "mrjam-admission-controller"
    "mrjam-intake-prepare" "mrjam-acceptance-mirror" "mrjam-acceptance-review"
    "mrjam-acceptance-merge" "mrjam-acceptance-sync" "mrjam-delivery-preparation"
    "mrjam-delivery-staging" "mrjam-promotion" "mrjam-validation-authority"
    "mrjam-validation-worker@" "mrjam-validation-collector@" "mrjam-validation-export@" ];
  overlay = { config, lib, pkgs, ... }: {
    imports = [ ./configuration.nix ];
    system.configurationRevision = revision;
    systemd.generators = lib.mkForce (builtins.removeAttrs before.systemd.generators [ "mrjam-first-cutover-guard" ]);
    # NixOS owns this stable include; the delivery transaction owns its target.
    environment.etc."nginx/nginx.conf".source = lib.mkOverride (-20)
      (pkgs.writeText "mrjam-nginx-entry.conf" "include /var/lib/mrjam-delivery/nginx-current.conf;\n");
    services.nginx.virtualHosts = lib.mapAttrs (_: _: {
      extraConfig = lib.mkAfter ''
        add_header X-Mrjam-Deployment "${revision}:blue" always;
      '';
    }) hosts;
    systemd.services = lib.genAttrs legacy (_: { enable = lib.mkForce false; }) // {
      mrjam-rust-blue = {
        restartIfChanged = false;
        stopIfChanged = false;
        wantedBy = lib.mkOverride (-20) [ "multi-user.target" ];
        serviceConfig.ExecStart = lib.mkOverride (-20)
          "${server}/bin/mrjam-server serve --config ${runtimes.blue}/runtime.json";
      };
      mrjam-rust-green = {
        restartIfChanged = false;
        stopIfChanged = false;
        wantedBy = lib.mkOverride (-20) [ "multi-user.target" ];
        serviceConfig.ExecStart = lib.mkOverride (-20)
          "${server}/bin/mrjam-server serve --config ${runtimes.green}/runtime.json";
      };
      mrjam-identity = {
        serviceConfig.ExecStart = lib.mkOverride (-20) (lib.replaceStrings
          [ before.services.mrjamIdentity.artifactStorePath ] [ "${server}" ]
          before.systemd.services.mrjam-identity.serviceConfig.ExecStart);
      };
      mrjam-identity-aliases = {
        serviceConfig.ExecStart = lib.mkOverride (-20) (lib.replaceStrings
          [ before.services.mrjamIdentity.artifactStorePath ] [ "${server}" ]
          before.systemd.services.mrjam-identity-aliases.serviceConfig.ExecStart);
      };
      mrjam-identity-deletion = {
        serviceConfig.ExecStart = lib.mkOverride (-20) (lib.replaceStrings
          [ before.services.mrjamIdentityDeletion.artifactStorePath ] [ "${server}" ]
          before.systemd.services.mrjam-identity-deletion.serviceConfig.ExecStart);
      };
      vise = {
        serviceConfig.ExecStart = lib.mkOverride (-20) "${vise}/server";
        environment.CARNET_DIST = lib.mkOverride (-20) "${vise}/dist";
      };
      nginx-config-reload = {
        # The delivery transaction validates and reloads the staged configuration.
        # Do not launch an independent asynchronous reload during system activation.
        enable = lib.mkForce false;
      };
    };
    systemd.timers = lib.genAttrs
      (lib.filter (name: builtins.hasAttr name before.systemd.timers) legacy)
      (_: { enable = lib.mkForce false; });
    # Bootstrap units belong only to system.control. Each release selects their
    # package, including when returning to a pre-bootstrap system generation.
    system.extraDependencies = [ engine units server frontends vise ] ++ builtins.attrValues runtimes
      ++ [ (builtins.storePath "/nix/store/dzwcbxfzzq41ipd23wy91hp309cg72z3-mrjam-protected-delivery-recipe-1") ];
  };
  configuration = baseline.evaluate [ overlay ];
  # The upstream generated Nginx config is also retained in its reload trigger.
  nginxTemplate = builtins.head configuration.systemd.services.nginx-config-reload.restartTriggers;
in {
  inherit configuration engine runtimes nginxTemplate;
  system = configuration.system.build.toplevel;
  nginx = configuration.services.nginx.package;
  postgresql = configuration.services.postgresql.finalPackage;
  postgresqlData = configuration.services.postgresql.dataDir;
}
