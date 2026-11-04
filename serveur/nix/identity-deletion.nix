{ pkgs, rustToolchain }:
let
  platform = pkgs.makeRustPlatform {
    cargo = rustToolchain;
    rustc = rustToolchain // { targetPlatforms = [ "x86_64-linux" ]; badTargetPlatforms = [ ]; };
  };
  source = pkgs.lib.cleanSourceWith {
    src = ../.;
    filter = path: type:
      !(builtins.elem (baseNameOf path) [ ".git" ".development" "target" "result" ])
      && pkgs.lib.cleanSourceFilter path type;
  };
in assert rustToolchain.version == "1.99.1";
platform.buildRustPackage {
  pname = "mrjam-identity-deletion";
  version = "0.1.0-transport2";
  src = source;
  cargoLock.lockFile = ../Cargo.lock;
  cargoBuildFlags = [ "--package" "mrjam-identity-deletion" ];
  cargoTestFlags = [ "--package" "mrjam-identity-deletion" ];
  doCheck = true;
  strictDeps = true;
  CARGO_BUILD_JOBS = "2";
  meta.platforms = [ "x86_64-linux" ];
}
