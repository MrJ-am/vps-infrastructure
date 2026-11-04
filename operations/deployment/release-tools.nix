# Fixed tool roots for the separately sealed release manifest. No activation.
let
  pkgs = import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source { system = "x86_64-linux"; };
  probes = import ./release-probes.nix { inherit pkgs; };
  bootstrap = builtins.storePath "/nix/store/8pkxq7pahlmhlmf6v890q2ica69cflsy-mrjam-forgejo-technical-bootstrap-1";
in {
  tools = {
    systemctl = "${pkgs.systemd}/bin/systemctl";
    nft = "${pkgs.nftables}/bin/nft";
    nix = "${pkgs.nix}/bin/nix";
    nix_store = "${pkgs.nix}/bin/nix-store";
    nix_env = "${pkgs.nix}/bin/nix-env";
    python = "${pkgs.python3}/bin/python3";
    curl = "${pkgs.curl}/bin/curl";
    tar = "${pkgs.gnutar}/bin/tar";
  };
  helpers = {
    capabilities = "${probes}/libexec/probe-standalone.py";
    obligations = "${probes}/libexec/preflight_obligations.py";
    forgejo_sso = "${probes}/libexec/forgejo_sso_probe.py";
    forgejo_probe = "${bootstrap}/bin/mrjam-forgejo-probe";
    forgejo_cleanup = "${bootstrap}/bin/mrjam-forgejo-cleanup";
  };
  ca_file = "/nix/store/l0avd78x86jr5swpayvz8a6z9y5g15z3-ca.pem/ca.pem";
  generator = "/nix/store/11gb9i2v7b3980zylx4pnr3wh7hd8djf-mrjam-first-cutover-boot-guard/bin/mrjam-first-cutover-guard";
}
