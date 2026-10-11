# Exploitation distante par l'infrastructure

Les runners GitHub Actions de vps-infrastructure disposent du mécanisme existant
scripts/connect.sh, environnement vps-production limité à main et secret
VPS_ADMIN_SSH_KEY. Réutiliser ce mécanisme ; aucun nouveau canal administratif.
La clé et ses valeurs ne doivent figurer dans aucun dépôt, log ou artefact.
La clé d'hôte publique est verrouillée dans scripts/ssh-known-hosts.

Les diagnostics et déploiements sont autorisés par la mission ; la préparation,
qualification, sauvegarde et le retour restent nécessaires. Les tests locaux et
le REPL SBCL dans Codex sont autorisés ; la limitation historique de Work ne les
restreint pas. Aucun REPL public ou associé aux données de production.

Le workflow monolithe-reference.yml n'accepte aucune commande libre et ne modifie
aucune donnée métier. Il relève metadata/agrégats sans secret ou contenu privé.
Pour reprendre : gh workflow run monolithe-reference.yml --repo MrJ-am/vps-infrastructure --ref main.
Lire son résultat identifié par commit et URL ; une compilation locale ne prouve
ni accès serveur ni déploiement. Le terminal hPanel reste le secours indépendant.

Les sources privées Vision et Signature sont accessibles à l'acteur de cette
session. Le token GITHUB_TOKEN d'un runner est normalement limité à son dépôt.
assemblage.yml accepte le credential de lecture COMPONENTS_READ_TOKEN si configuré,
sans le recopier dans les sources ou journaux ; sa disponibilité doit être constatée.
Aucune nouvelle visibilité publique ou copie source divergente n'est utilisée.

Les APIs de protections de branche, secrets et deploy keys ont répondu 403 à
l'intégration lors de l'inventaire. Leur inspection/retrait distant éventuel
nécessite la capacité correspondante ; ne pas prétendre les avoir nettoyées.
Les sauvegardes, rôles, services tiers et générations de retour sont conservés.
