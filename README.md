# Infrastructure VPS

Configuration commune du VPS NixOS Hostinger `187.77.95.158` pour héberger
plusieurs applications derrière une seule instance Nginx et partager une
instance PostgreSQL 17 entre les projets qui en ont besoin.

**État actuel : l'interface ElmUI de Vision est publiée depuis le 21 septembre 2026 à 22:32 UTC.**
Voir [la publication vérifiée](docs/VISION-INTERFACE.md) et [l'état du VPS](docs/ETAT.md).

**Migration initiale : migration activée et enregistrée le 18 septembre 2026 à 21:10 UTC.**
La [bascule vérifiée](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395320446)
confirme les services, les données, les accès et les sauvegardes. Les sources
installées correspondent à `fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb`.
Le relais côté Mémoire est fusionné dans la [PR nº 8](https://github.com/MrJ-am/M-moire/pull/8).
Lire [l'état attesté](docs/ETAT.md) pour les générations et les preuves.

**Accès depuis ChatGPT Work : GitHub Actions.** Work prépare les changements
et consulte les résultats ; les runners GitHub ouvrent les connexions SSH au
VPS. Ne pas chercher à rétablir un accès SSH direct depuis Work. Le workflow
manuel [Auditer le VPS](.github/workflows/audit.yml) utilise les scripts de
lecture seule ; sa configuration initiale est détaillée dans
[ACCES.md](docs/ACCES.md). Il n'active pas la migration.

| Ce dépôt | Chaque projet applicatif |
|---|---|
| NixOS, démarrage, réseau, SSH, pare-feu | Code, tests et contenu |
| Nginx sur 80/443, certificats HTTPS | Service HTTP sur une adresse locale |
| Attribution des domaines, alias et ports | Publications avec son compte dédié |
| Intégration des modules applicatifs revus | Proposition d'évolution de son module |
| PostgreSQL, création des bases et rôles, contrôle des accès | Schéma, données et migrations applicatives |
| Sauvegardes locales PostgreSQL et contrôles collectifs | Exports chiffrés hors VPS existants et validation des restaurations |

`projects.json` attribue chaque domaine et chaque port à un seul projet.
`modules/gateway.nix` et `lib/virtual-hosts.nix` construisent le routage.
`apps/` active les services avec leurs paramètres d'instance. `vendor/`
contient les modules applicatifs revus et leur provenance exacte.
`hosts/hostinger/` conserve les réglages du VPS relevés dans Matheval.

`databases.json` réserve les bases indépendamment du routage HTTP.
`modules/postgresql.nix` possède l'instance, les accès par socket Unix et les
sauvegardes quotidiennes. Une application ne peut se connecter qu'à sa base
avec son compte système dédié. Le port PostgreSQL n'écoute pas en TCP.
Lire [le contrat PostgreSQL](docs/POSTGRESQL.md) et
[le message de reprise pour Mémoire](docs/MESSAGE-MEMOIRE.md).

La copie Matheval correspond exactement au module amont du commit
`0bcdaf101cbdacb85694ca217fd21ab3f2eac828` de Mémoire. L'adaptation PostgreSQL
a été reprise dans ce module : ne plus lui appliquer
`patches/matheval-postgresql.patch`. Ce patch et ses empreintes antérieures
restent conservés comme historique réversible. Vision et sa base sont activés ; son interface ElmUI est servie par le module
`apps/vision-interface.nix`. Lire [l'état courant](docs/ETAT.md).

Le raccordement initial reste `https://principiipetit.io/matheval/` vers
`http://127.0.0.1:3000`, sans retirer le préfixe. `www` et les redirections
existantes sont conservés. Les deux certificats et leurs emplacements restent
gérés par les mêmes options NixOS. Aucun changement de DNS n'est nécessaire
pour cette séparation.

La configuration issue de Mémoire a été comparée au VPS réel et construite avec
son Nixpkgs installé, sans mise à jour. Lire [la procédure de migration](docs/MIGRATION.md).
`check.yml` et `audit.yml` contrôlent ; `migration.yml` prépare sans activer ;
`activate-migration.yml` effectue le plan, l'essai protégé et l'enregistrement
sur demande explicite. Ces scripts de migration sont dédiés à la bascule initiale.

```sh
sh scripts/check.sh
python3 scripts/probe.py --output /chemin/prive/avant.json
python3 scripts/probe.py --baseline /chemin/prive/avant.json
```

La première commande exige Python 3 et Nix. Les deux suivantes utilisent
seulement la bibliothèque standard Python et vérifient les certificats TLS.
Elles effectuent exclusivement des GET publics : aucune participation ou
connexion administrateur n'est créée. Le relevé contient des codes HTTP,
redirections et empreintes de fichiers publics, jamais les réponses privées.

La CI vérifie les registres, le routage, l'évaluation NixOS complète avec et
sans une seconde base, puis les accès et les restaurations dans un PostgreSQL
17 jetable. Son Nixpkgs de validation est identifié dans `tests/nixpkgs.json` ;
il ne remplace pas celui du VPS. Le workflow `check.yml` ne reçoit aucune clé
root et ne déploie pas automatiquement. L'accès administratif du workflow
manuel `audit.yml` est distinct, dans l'environnement `vps-production`.
La migration initiale a également été construite et vérifiée sur le VPS réel.
Toute nouvelle évolution du système exige un nouvel audit et son propre plan.

Pour ajouter une application, suivre [le contrat d'intégration](docs/AJOUTER-UN-PROJET.md).
Pour les accès, lire [ACCES.md](docs/ACCES.md).
Pour le raccordement statique préparé de `logique.echos.systems`, lire
[LOGIQUE.md](docs/LOGIQUE.md). Les candidats ACME/HTTPS sont distincts de la
configuration courante ; leur présence ne signifie pas qu'ils sont activés.

Une passerelle unique reste un point commun à tous les sites. Les validations,
les comptes distincts et le retour arrière réduisent les risques ; ils ne
garantissent pas une absence absolue d'interruption ou de saturation du VPS.

Références techniques : [activation de NixOS](https://nixos.org/manual/nixos/stable/#sec-changing-config),
[contrôle et rechargement de Nginx](https://nginx.org/en/docs/control.html).
