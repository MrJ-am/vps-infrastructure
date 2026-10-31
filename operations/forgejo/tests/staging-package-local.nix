let pkgs = import /nix/store/ydk30pf7qngrw0ws113m9p005p681rxy-source { system = "x86_64-linux"; }; in pkgs.callPackage /workspace/vps-infrastructure/operations/forgejo/staging-package.nix { }
