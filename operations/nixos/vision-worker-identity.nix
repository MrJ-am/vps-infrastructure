# Shared closed configuration contract for separately qualified worker versions.
# Legacy remains available only to reproduce the historical receipts.
{ lib, cfg }:
let
  native = cfg.identityProtocol == "kanidm-native";
  private = lib.types.strMatching "/(run/secrets|run/keys|var/lib)/[A-Za-z0-9_./-]+";
  caType = lib.types.strMatching "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+(/[A-Za-z0-9+._?=-]+)*";
  credentialFile = if native then cfg.kanidmCredentialFile else cfg.keycloakCredentialFile;
  credentialName = if native then "kanidm" else "keycloak";
  canonical = path: path != null && !(lib.hasInfix "//" path)
    && !(lib.hasSuffix "/" path)
    && lib.all (part: part != "." && part != "..") (lib.splitString "/" path);
in {
  inherit native credentialFile credentialName;
  options = {
    identityProtocol = lib.mkOption { type = lib.types.enum [ "keycloak-legacy" "kanidm-native" ]; default = "keycloak-legacy";
      description = "Exact protocol of the selected prebuilt worker; never inferred from a credential filename."; };
    keycloakCredentialFile = lib.mkOption { type = lib.types.nullOr private; default = null; };
    kanidmCredentialFile = lib.mkOption { type = lib.types.nullOr private; default = null; };
    kanidmCaFile = lib.mkOption { type = lib.types.nullOr caType; default = null;
      description = "Qualified immutable public CA bundle, with no symlinks."; };
    kanidmCaSha256 = lib.mkOption { type = lib.types.nullOr (lib.types.strMatching "[0-9a-f]{64}"); default = null; };
  };
  configuration = name: if native then {
    kanidm_file = "/run/credentials/${name}.service/kanidm";
    kanidm_ca_file = cfg.kanidmCaFile;
    kanidm_ca_sha256 = cfg.kanidmCaSha256;
  } else { keycloak_file = "/run/credentials/${name}.service/keycloak"; };
  credential = "${credentialName}:${if credentialFile == null then "/invalid-unconfigured-credential" else credentialFile}";
  assertions = [
    { assertion = canonical credentialFile;
      message = "Vision worker requires a canonical private credential reference for its explicitly selected identity protocol."; }
    { assertion = if native then cfg.keycloakCredentialFile == null && canonical cfg.kanidmCaFile
          && cfg.kanidmCaSha256 != null && !(builtins.hasContext cfg.kanidmCaFile)
        else cfg.kanidmCredentialFile == null && cfg.kanidmCaFile == null && cfg.kanidmCaSha256 == null;
      message = "Vision worker identity protocols cannot be mixed; native Kanidm requires a qualified public CA file and exact SHA-256."; }
  ];
  extraDependencies = lib.optionals (native && cfg.kanidmCaFile != null)
    [ (builtins.storePath (lib.concatStringsSep "/" (lib.take 4 (lib.splitString "/" cfg.kanidmCaFile)))) ];
}
