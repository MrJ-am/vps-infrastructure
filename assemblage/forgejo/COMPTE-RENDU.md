# Forgejo — Kanidm seul et quotas, 16 octobre 2026

**https://forge.mrj.am/** est déployé avec **Kanidm comme seule connexion Web**,
via **https://log.mrj.am/**. Le compte administrateur est **MrJam**, même identifiant
interne et droits conservés, rattaché par UUID à l'identité propriétaire existante.
Les facteurs MFA du propriétaire n'ont pas été réinitialisés.

Les formulaires et authentifications locales par mot de passe sont désactivés
côté serveur, ainsi que l'ancien OpenID. Le fichier de mot de passe initial a été
supprimé. Inscription locale fermée, création de compte ordinaire après une
connexion Kanidm autorisée, aucun rapprochement automatique par courriel.
Clés SSH2222 et jetons HTTPS restent disponibles pour les opérations Git/API.

Versions conservées : Forgejo16.0.3, Pandoc3.7.0.2, MathJax/polices4.1.3,
Kanidm de production1.11.2. Moteur Pandoc, MathJax local et assainissement inchangés.
Nixpkgs et dépendances restent verrouillés ; aucun runner ou workflow supplémentaire.
Le VPS utilise son entrée NixOS classique, sans flake ; imports existants préservés.

## Gestion des limites

- Nombre de dépôts : défaut global Nix, surcharge par personne depuis
  Administration → Comptes utilisateurs → Modifier.
- Stockage total par personne/groupe : moteur de quotas activé, API native et
  `scripts/forgejo-quotas.py` fournis. Vue d'utilisation dans les paramètres du compte.
- Défauts actuellement **illimités**, aucune limite chiffrée imposée à cette étape.
  Les options Nix `infrastructure.forgejo.quotas.maxRepositories` et `totalStorage`
  permettent une politique globale reproductible ; les exceptions sont sauvegardées
  avec PostgreSQL. [Guide et commandes](SSO-QUOTAS.md).

Le stockage natif limite le total d'un propriétaire, pas strictement chaque dépôt.
Une écriture peut dépasser le seuil avant blocage des suivantes. Le plafond de
nombre est effectif, mais son refus via l'API16.0.3 renvoie500 au lieu de4xx ;
ce comportement amont est documenté et testé, sans modification fragile du programme.
Les administrateurs sont exemptés du plafond de nombre de dépôts.

## Tests effectués

Construction NixOS avant activation, comparaison des unités et des hôtes, règles
PostgreSQL et timers TLS conservés ; sauvegardes existantes restaurées isolément.
La bascule SSO n'a redémarré ni PostgreSQL ni les services protégés.25sondes
HTTP/TLS existantes passent après déploiement et persistance.

En production : Chromium avec TLS vérifié, pas de formulaire de mot de passe,
POST local et Basic refusés, un seul fournisseur, redirection réelle vers
`log.mrj.am` avec le bon client/retour et PKCE S256. Interface Log mobile inspectée,
sans erreur JavaScript ; découverte native annonçant ES256. Compte MrJam et
rattachement par UUID vérifiés sans publier l'identifiant personnel.

API de gestion des quotas exercée avec règle temporaire affectée à personne puis
supprimée. Dépôt privé `MrJam/org-validation`, clone/push HTTPS et SSH réussis ;
clé et jeton de test révoqués. Ancien dépôt privé de validation préservé.
Après redémarrage Forgejo : même commit, PID des autres services conservés,
sauvegarde déchiffrée puis restaurée dans un PostgreSQL isolé sans TCP,
**130 tables aux empreintes identiques et deux dépôts vérifiés par git fsck**.
Aucune donnée de production restaurée. La politique SSO reste active après reprise.

En isolation : vrai Forgejo16.0.3 et vrai Kanidm1.11.1 du Nixpkgs verrouillé,
sessions MFA, code/PKCE/échange et vérification ES256 réels, rattachement du compte
existant, création externe non administratrice, renommage conservant l'identifiant,
refus des mots de passe, plafonds de nombre et stockage, surcharges par compte/groupe.
L'étape UI IdP de ce test est médiée par son API native, pas par une personne.
Les tests historiques Chromium Org/CHTML, mobile, injections, liens et images restent
consultables dans `qualification-production.json` ; cette configuration est conservée.

**Non effectué : connexion personnelle MFA du propriétaire sur la production.**
Utiliser le bouton Kanidm de Forgejo avec les identifiants Log habituels pour la
première connexion ; le compte Forgejo associé est MrJam. Aucun secret personnel
n'est demandé par l'agent. Aucun redémarrage complet du VPS n'a été effectué.

## Sources et exploitation

Source déployée : `ac739eedcffc32d2fba29f4ce5b124e6c291b642`, génération `zm6k63jq`.
Nix : `module.nix`, `integration.nix`, `assets.nix`. Raccordement : `sso.py`,
`qualification-sso.py`, opérateurs et testeurs `scripts/forgejo-*.py`.
[Déploiement](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38895153571) ·
[Git et quotas](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38895359486) ·
[Persistance/restauration](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38895497132).
Reçus détaillés : `qualification-sso-production.json`, `qualification-sso-locale.json`.

Secret OIDC root uniquement, fichier0600/répertoire0700, hors Git/store/arguments ;
sa valeur n'est jamais publiée. Sauvegarde quotidienne chiffrée à04:45UTC (+0–10min),
rétention30jours, maintenant avec l'état OIDC. Destination hors VPS restant à raccorder.
Mail sortant désactivé. La suspension Kanidm n'est pas une révocation instantanée
des sessions et accès Git existants : bloquer aussi le compte Forgejo lors d'un retrait.
La procédure et les limites précises sont dans [SSO-QUOTAS.md](SSO-QUOTAS.md).
