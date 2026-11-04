# Match Signature's reviewed requirements; sources are fixed-output downloads.
{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  python=pkgs.python3.override {packageOverrides=final: prev: {
    skia-pathops=prev.skia-pathops.overridePythonAttrs (_: {
      version="0.9.2";
      src=pkgs.fetchurl {
        url="https://files.pythonhosted.org/packages/4a/f6/ab37d6fa21f25965d4ad059745c76f13ddfb92a2c06a842a42ad77961c24/skia_pathops-0.9.2.tar.gz";
        sha256="4b6d8459f6f4a69282cb26fca0c2bb0b321cc58a9bf9cc6579a52a391edc0319";
      };
    });
    uharfbuzz=prev.uharfbuzz.overridePythonAttrs (_: {
      version="0.56.1";
      src=pkgs.fetchurl {
        url="https://files.pythonhosted.org/packages/60/77/48457fb0c51f6f8c1e3082b126322e075d60fea60ee0df2b18cc050d9874/uharfbuzz-0.56.1.tar.gz";
        sha256="a0a6928ed66b166a931ebe5df9ac551b9c42983513030233dcd95b41fa827f97";
      };
    });
  };};
in python.withPackages (p: [p.fonttools p.brotli p.skia-pathops p.uharfbuzz])
