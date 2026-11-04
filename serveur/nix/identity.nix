{ pkgs, rustToolchain }:
let
  platform = pkgs.makeRustPlatform {
    cargo = rustToolchain;
    rustc = rustToolchain // {
      targetPlatforms = [ "x86_64-linux" ];
      badTargetPlatforms = [ ];
    };
  };
  source = pkgs.lib.cleanSourceWith {
    src = ../.;
    filter = path: type:
      let
        name = baseNameOf path;
        relative = pkgs.lib.removePrefix ((toString ../.) + "/") path;
      in !(builtins.elem name [ ".git" ".development" "target" "result" ])
        && !(relative == "docs" || pkgs.lib.hasPrefix "docs/" relative)
        && !(builtins.elem relative [ "README.org" "crates/identity/README.org" ])
        && pkgs.lib.cleanSourceFilter path type;
  };
in platform.buildRustPackage {
  pname = "mrjam-identity";
  version = "0.1.0";
  src = source;
  cargoLock.lockFile = ../Cargo.lock;
  nativeBuildInputs = [ pkgs.pkg-config ];
  buildInputs = [ pkgs.sqlite ];
  cargoBuildFlags = [ "--package" "mrjam-identity" ];
  cargoTestFlags = [ "--package" "mrjam-identity" ];
  doCheck = true;
  strictDeps = true;
  meta = {
    description = "Native Kanidm browser-session and OAuth MCP broker";
    mainProgram = "mrjam-identity";
    platforms = [ "x86_64-linux" ];
  };
}
