# Site Vision et connexion commune mrj.am

Le navigateur Vision 1.3 est servi sur `https://vision.mrj.am/`, avec lecture et
édition des fiches, données qualitatives, paramètres, tags, filtres et tris.
Sa migration 004 est additive et conserve les observations originales.

## Sessions

`modules/mrj-auth.nix` gère le service local `mrj-auth` sur 127.0.0.1:3002.
Ses sessions sont stockées dans `/var/lib/mrj-auth/sessions.sqlite` (0700 pour
le répertoire) sous forme de condensats des jetons. Le cookie
`__Secure-mrj_session` est Secure, HttpOnly, SameSite=Lax, Path=/, Domain=mrj.am.
La durée maximale est de douze heures, avec deux heures d'inactivité. Une
connexion renouvelle le jeton ; la déconnexion le révoque pour tous les sites
raccordés. Le changement du fichier d'identifiants invalide les sessions.

Le fichier d'identifiants existant `/var/lib/vision/auth/htpasswd` reste la
source des comptes (SHA-512 crypt, vérifié par Passlib). Il n'est ni déplacé,
ni remplacé par cette opération. Les comptes de verrouillage sont refusés,
et le fichier Mobile Live ne sert jamais à se connecter au site.

Ajouter `browserAuth: true` à un projet du registre sous `mrj.am` fournit les
mêmes routes `/auth/session`, `/auth/login`, `/auth/logout` et protège
`/api/web/` avec cette session. Le registre réserve le port 3002. Les domaines
d'autres propriétaires ne peuvent pas participer à ce cookie. Les applications
sous mrj.am sont considérées comme appartenant au même périmètre de confiance.

Nginx vérifie la session par sous-requête interne. Tout POST à `/api/web/`
exige un jeton CSRF associé à la session et une origine HTTPS identique au site.
Les en-têtes d'identité sont écrasés ; mot de passe, cookie et CSRF ne sont pas
transmis à Vision. Les appels Basic à `/api/v1/` et `/mcp` restent inchangés.
Les pages et scripts de l'interface ne contiennent aucune donnée personnelle.

## Première activation

Cette opération possède ses propres scripts et ne réutilise pas les gardes de
la migration 1.1 → 1.2. Le script `vision-web-prepare.py` exige Vision 1.2.0 au
commit 445f9d7e6944d621de33283ca960d772813f47a2, compare la configuration active,
conserve les sources, la génération, les identifiants et des sauvegardes age
des deux bases, puis construit avec le Nixpkgs déjà installé.

1. CI verte, puis intégration du candidat sur main.
2. Workflow **Préparer le site Vision et la connexion commune**.
3. Lire le rapport et le dry-run ; seules les unités Vision, Nginx et le
   nouveau service de sessions doivent être concernées.
4. Workflow **Activer le site Vision et la connexion commune**, avec le SHA
   exact préparé. Un timer systemd indépendant arme un retour à quinze minutes.
   La version est testée ; une nouvelle connexion SSH et les contrôles publics
   précèdent l'enregistrement du démarrage.

Un compte de sonde aléatoire est ajouté temporairement au fichier existant,
sans remplacer les comptes. Il vérifie HTTPS, l'ancienne API, la connexion,
CSRF, la lecture PostgreSQL et la révocation. Le fichier original est restauré
avant la fin des contrôles. Le secret ne quitte pas le processus de vérification,
et aucune donnée fictive n'est créée. Le retour rétablit la génération, les
sources, le lien applicatif et les identifiants ; il ne restaure aucun dump et
n'efface aucune table.

## Reprise du premier essai

L'[essai du 20 septembre 2026](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35541277939)
sur `7f7697227be70bd3dd0847a17851a9b1cbb81e79` a rétabli la génération précédente :
OpenSSL n'était pas disponible dans l'environnement du processus de sonde.
Le workflow fournit désormais cette dépendance et la sonde est préparée avant
toute activation. La reprise valide le `rollback.json` de cet essai précis,
la génération, la configuration, le lien applicatif et les identifiants
rétablis. Elle exige l'absence de toute session et l'arrêt du service SSO,
conserve la base de sessions initialisée et désarme l'ancien timer avant de
préparer une nouvelle opération. Elle refuse un essai déjà enregistré.

Le [second essai](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35541638104)
sur `b71058c99e65aa3d25a8f116cc18d256988a58fd` a validé la connexion, les lectures,
CSRF, la révocation et les 22 sondes HTTP. Il est revenu à la génération
précédente parce que le contrôle des sauvegardes cherchait le timer global.
Avec `backupAll = false`, NixOS installe un timer par base :
`postgresqlBackup-matheval.timer` et `postgresqlBackup-vision.timer`.
Leur présence est désormais vérifiée dans l'évaluation NixOS et leur activité
est exigée dès la préparation, puis après activation. La reprise identifie
désormais ce second essai et conserve les mêmes conditions de retour complet.

## Identifiants durables

L'activation précédente du 20 septembre utilisait un verrou de bootstrap dont
le mot de passe n'a pas été conservé. Le rapport de cette opération indique
`durable_credentials: false` si ce verrou est toujours le seul compte.
Il faut alors définir `VISION_API_USERNAME` et `VISION_API_PASSWORD` dans
l'environnement GitHub `vps-production`, puis lancer le workflow existant
**Renouveler les identifiants Vision**. Le même compte ouvre ensuite le site
et l'API générale. Ne jamais saisir ces secrets dans Git ou un journal.

## Vérifications

La CI évalue NixOS, les routes et les deux bases. `test_mrj_auth.py` teste les
sessions entre deux sous-domaines, les origines, CSRF, expiration, rotation,
révocation, tentatives de connexion et une véritable passerelle Nginx dont
les emplacements sont directement évalués depuis le module Nix. La CI Vision
vérifie les opérations du navigateur avec PostgreSQL 17 et les contrats MCP.
