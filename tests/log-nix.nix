{ cheminBrut ? false }:
let
  lib = import <nixpkgs/lib>;
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ ../hosts/hostinger/configuration.nix ({ pkgs, ... }: {
      infrastructure.identite = { enable = true; preconditionsValidees = true; };
      infrastructure.visionMultiutilisateur.enable = true;
      infrastructure.courriel.enable = true;
      infrastructure.visionCycle.enable = true;
      infrastructure.admission.enable = true;
      infrastructure.fermeture.enable = true;
      infrastructure.metier = { enable = true; bankVersion = "fixture";
        paquet = pkgs.writeShellScriptBin "mrjam-metier" "exit 125"; };
      infrastructure.log = { enable = true;
        paquet = if cheminBrut then builtins.storePath "/nix/store/0aqnq3k20yq30hf0bch64ghy3nj9bd66-kanidm-1.11.2"
          else import ../assemblage/kanidm/artefact.nix { inherit pkgs;
            artefact = "/nix/store/0aqnq3k20yq30hf0bch64ghy3nj9bd66-kanidm-1.11.2"; }; };
    }) ];
  }).config;
  v = c.services.nginx.virtualHosts;
in
assert builtins.stringLength (toString c.system.build.toplevel) > 32;
assert builtins.all (a: a.assertion) c.assertions;
assert !c.services.keycloak.enable && !c.systemd.services.keycloak.enable;
assert !c.systemd.services.mrj-auth.enable;
assert c.systemd.services.kanidm.enable && c.services.kanidm.server.enable;
assert c.systemd.services.kanidm.serviceConfig.User == "kanidm";
assert c.systemd.services.kanidm.serviceConfig.StateDirectoryMode == "0700";
assert c.services.kanidm.server.settings.adminbindpath == "/run/kanidmd/admin.sock";
assert c.services.kanidm.server.settings.online_backup.versions == 0;
assert lib.hasInfix "pg_dump --host=/run/postgresql --format=custom" c.systemd.services.mrjam-sauvegarde.script;
assert lib.elem "kanidm.service" c.systemd.services.mrjam-sauvegarde.after;
assert lib.elem "kanidm.service" c.systemd.services.mrjam-sauvegarde.requires;
assert lib.elem "/var/lib/kanidm" c.systemd.services.mrjam-sauvegarde.serviceConfig.ReadWritePaths;
assert lib.hasInfix "runuser -u kanidm --" c.systemd.services.mrjam-sauvegarde.script;
assert lib.hasInfix "test -s \"$native\"" c.systemd.services.mrjam-sauvegarde.script;
assert lib.hasInfix "mrj_identite mrjam-metier vision_identite" c.services.postgresql.identMap;
assert v."vision.mrj.am".locations."= /_vision_administration".proxyPass == "http://unix:/run/mrjam-metier/http.sock:/verify-gestion";
assert v."vision.mrj.am".locations."= /_vision_mcp_token".proxyPass == "http://unix:/run/mrjam-metier/http.sock:/verify-mcp";
assert lib.hasInfix "proxy_ssl_verify on" v."log.mrj.am".locations."/".extraConfig;
assert lib.hasInfix "proxy_ssl_verify_depth 2;" v."log.mrj.am".locations."/".extraConfig;
assert v."log.mrj.am".locations."/".return == null;
assert v."log.mrj.am".locations."^~ /v1/raw/".return == "404";
assert v."log.mrj.am".locations."^~ /realms/".return == "410";
assert lib.all (n: !(lib.hasInfix "3002" (v."vision.mrj.am".locations.${n}.proxyPass or "")))
  [ "/auth/" "^~ /oauth/" "= /_mrj_session" "= /_vision_administration" "= /_vision_mcp_token"
    "= /.well-known/oauth-authorization-server" "= /.well-known/oauth-protected-resource/mcp" ];
assert !(v."vision.mrj.am".locations ? "/oauth/");
{ generationEvaluee = true; kanidmSepare = true; clientLisp = true; keycloakActif = false;
  tlsVerifie = true; processusMetier = 1; production = false; }
