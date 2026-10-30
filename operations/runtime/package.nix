# Construct only public runtime configuration around already built outputs.
{ lib, runCommand, python3, coreutils
, configFile
, slot
, serverStorePath
, serverManifestSha256
}:
let
  storePattern = "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+";
  validStore = value: builtins.isString value && !(builtins.hasContext value)
    && builtins.match storePattern value != null;
  configuration = builtins.fromJSON (builtins.readFile configFile);
  assetPaths = map (asset: asset.directory) configuration.assets;
  caRoot = if (configuration.log or null) == null then [ ] else
    [ (lib.concatStringsSep "/" (lib.take 4 (lib.splitString "/" configuration.log.ca_file))) ];
  referencedPaths = [ serverStorePath ] ++ assetPaths ++ caRoot;
  references = map builtins.storePath referencedPaths;
  server = builtins.storePath serverStorePath;
in
assert builtins.elem slot [ "blue" "green" ];
assert lib.all validStore referencedPaths;
assert builtins.match "[0-9a-f]{64}" serverManifestSha256 != null;
runCommand "mrjam-runtime-${slot}" {
  nativeBuildInputs = [ python3 coreutils ];
  # These inputs must already be present. This expression contains no fetcher
  # or application build, and keeps the exact asset/server closure reachable.
  existingReferences = lib.concatStringsSep "\n" references;
} ''
  mkdir -p "$out"
  cp ${configFile} "$out/runtime.json"
  ${server}/bin/mrjam-server check-config "$out/runtime.json" > /dev/null
  ${python3}/bin/python3 -I -S ${./verify_configuration.py} \
    "$out/runtime.json" ${lib.escapeShellArg slot} \
    ${lib.escapeShellArg serverStorePath} ${lib.escapeShellArg serverManifestSha256} \
    > "$out/configuration-manifest.json"
''
