# Liens Org utilisables dans Forgejo et Emacs

Les sources conservent la syntaxe Org relative, par exemple
`[[file:docs/mathematiques.org][Mathématiques]]` dans `README.org`,
`[[file:structure.org][document voisin]]` et `[[file:../README.org][Accueil]]`
dans `docs/`. Ces chemins restent relatifs au fichier dans Emacs ; aucune URL
Forgejo, branche ou domaine n'est ajouté aux documents.

## Cause et correction

Pandoc conservait correctement `href="docs/mathematiques.org"`. Forgejo 16.0.3
post-traite les images d'un moteur externe, mais ne résout pas ses liens HTML
ordinaires contre le répertoire Git. Sur `/MrJam/org-validation`, le navigateur
résolvait donc ce chemin en `/MrJam/docs/mathematiques.org`, hors du dépôt.
Ouvrir directement `/MrJam/org-validation/src/branch/main/README.org` masquait
le défaut. Les anciens tests ouvraient les documents directement et vérifiaient
un lien de retour ; ils ne cliquaient pas ceux du README intégré.

`org-links.lua`, filtre Pandoc versionné, préfixe seulement les liens relatifs
rendus avec `GITEA_PREFIX_SRC`, variable fournie par le moteur externe Forgejo.
Elle contient le dépôt, la branche ou le commit et le répertoire du document.
Les chemins `../` restent résolus normalement par le navigateur. Les ancres,
URL avec schéma, chemins absolus et images ne sont pas modifiés. Le traitement
Forgejo des images et l'assainissement HTML restent activés ; le filtre ne crée
aucun script et n'est pas chargé depuis les dépôts hébergés.

Le module Nix référence le filtre dans le store ; le transport de déploiement
inclut explicitement les fichiers Lua. Aucune modification de template interne,
de dépendance ou de document utilisateur n'est nécessaire. La qualification
n'écrase plus les fichiers existants du dépôt de validation.

## Vérification

`qualification-liens-locale.json` consigne 28 clics réels Chromium : README
intégré à la racine avec/sans slash, vue de branche, fichier README ouvert,
lien voisin et retour au parent, aux largeurs 1280 et 390 pixels. Les pages
cibles contiennent du HTML interprété ; les formules sont effectivement
composées en CHTML. Les huit contrôles de documents, images, assainissement,
confidentialité et absence d'erreur JavaScript/ressource passent aussi.

La qualification de production utilise le vrai moteur et son assainissement
via l'API native `/markup`, puis vérifie l'existence des destinations privées
via l'API authentifiée. Elle ne prétend pas effectuer la connexion MFA
personnelle du propriétaire dans l'interface Web de production.

Emacs 30.2 / Org 9.7.11 a ouvert les six liens inter-documents des sources
originales via `org-open-at-point`, sans modification. Le contrôle reproductible
est `scripts/forgejo-liens-emacs.el` ; résultat dans le reçu local.
