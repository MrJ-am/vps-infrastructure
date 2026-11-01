{ ... }: { imports = [ (import ./payload/integration.nix { baseConfiguration = ./base.nix; }) ]; }
