# Infrastructure VPS

Configuration commune du VPS NixOS Hostinger `187.77.95.158` pour héberger
plusieurs applications derrière une seule instance Nginx et partager une
instance PostgreSQL 17 entre les projets qui en ont besoin.

**État : préparé, pas encore installé sur le VPS.** Le dépôt GitHub privé
est [MrJ-am/vps-infrastructure](https://github.com/MrJ-am/vps-infrastructure). Le relais côté mémoire est
préparé dans la [PR nº 8](https://github.com/MrJ-am/M-moire/pull/8), en brouillon.

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
restent conservés comme historique réversible. Vision dispose seulement
d'un exemple de réservation ; aucune base Vision n'est activée à ce stade.

Le raccordement initial reste `https://principiipetit.io/matheval/` vers
`http://127.0.0.1:3000`, sans retirer le préfixe. `www` et les redirections
existantes sont conservés. Les deux certificats et leurs emplacements restent
gérés par les mêmes options NixOS. Aucun changement de DNS n'est nécessaire
pour cette séparation.

La configuration provient du dépôt du mémoire, pas d'un nouvel audit du VPS.
Lire [l'état attesté](docs/ETAT.md), puis [la procédure de migration](docs/MIGRATION.md).
Les scripts fournis contrôlent la configuration ; aucun n'active NixOS.

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
Une construction NixOS complète et un audit restent requis sur le VPS.

Pour ajouter une application, suivre [le contrat d'intégration](docs/AJOUTER-UN-PROJET.md).
Pour les accès, lire [ACCES.md](docs/ACCES.md).

Une passerelle unique reste un point commun à tous les sites. Les validations,
les comptes distincts et le retour arrière réduisent les risques ; ils ne
garantissent pas une absence absolue d'interruption ou de saturation du VPS.

Références techniques : [activation de NixOS](https://nixos.org/manual/nixos/stable/#sec-changing-config),
[contrôle et rechargement de Nginx](https://nginx.org/en/docs/control.html).
