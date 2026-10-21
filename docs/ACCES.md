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
Le credential de lecture COMPONENTS_READ_TOKEN a été créé et sa disponibilité
constatée par le run 38118779445. Ne pas le recopier dans les sources ou journaux.
L'ancien assemblage.yml de qualification automatique est maintenant désactivé et
archivé ; son remplacement de promotion doit respecter DEVELOPPEMENT.md.
Aucune nouvelle visibilité publique ou copie source divergente n'est utilisée.

Les APIs de protections de branche, secrets et deploy keys ont répondu 403 à
l'intégration lors de l'inventaire. Leur inspection/retrait distant éventuel
nécessite la capacité correspondante ; ne pas prétendre les avoir nettoyées.
Les sauvegardes, rôles, services tiers et générations de retour sont conservés.

Pour retrouver le nom Log et le mail du propriétaire, l'opération fermée
`retrouver-identite` de `log-deploiement.yml` lit les seules métadonnées du plan
et les croise avec `log_principaux` ouvert en lecture seule. Le résultat est
chiffré RSA4096/OAEP-SHA256 pour la clé publique PEM/base64 fournie dans
`destinataire_identite`. Garder la clé privée dans l'atelier ; aucun identifiant,
mail, UUID ou authentificateur en clair dans le dépôt, les logs ou les artefacts.
Ce relevé ne récupère aucun compte administrateur et ne modifie pas l'IdP.
