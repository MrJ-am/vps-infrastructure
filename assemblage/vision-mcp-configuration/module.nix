{ config, ... }: {
  # Même valeur que modules/metier.nix, ajoutée à la génération déjà installée.
  systemd.services.mrjam-metier.environment.VISION_PUBLIC_MCP_URL =
    "https://${config.services.vision.domain}/mcp";
}
