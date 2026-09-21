# État attesté au 21 septembre 2026

## Logique : reprise de la préparation, aucune activation

Le site `logique.echos.systems` est préparé sur `preparation/logique-vps`.
L'[audit nº 35637628338](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35637628338),
commit `ba66dfcf939f299f9a296658aeaab938366b719e`, a réussi à 18:19 UTC :
22 contrôles HTTP/TLS existants, DNS A `187.77.95.158` sans AAAA, générations
identiques et seconde connexion du runner. Aucun certificat Logique ni
publication au chemin alors contrôlé (`/srv/apprendre-a-demontrer/current`)
n'était présent ; le nouveau précontrôle examine aussi `/srv/logique/current`.

Le nouveau lot ajoute les candidats ACME puis HTTPS, les contrôles statiques
et une préparation manuelle distincte de toute activation.
L'archive applicative `10652278750`, révision `52a3d4b7714608e09561728508818525b53aacda`,
a été vérifiée : ZIP et 75 fichiers `dist` conformes. Les réserves
typographiques et de publication restent à lever dans le mécanisme collectif.
Le workflow de construction VPS n'a pas été exécuté pendant cette reprise.
La [CI nº 35656506154](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35656506154)
a réussi au commit `b722165485e9b3b325b150f05ae7da5919a57984` : 55 tests,
Nginx réel, évaluations NixOS complètes des deux phases et des invariants,
ainsi que PostgreSQL 17 et ses restaurations isolées.
Lire [LOGIQUE.md](LOGIQUE.md) pour les références, les preuves et les étapes restantes.

## Vision web et sessions mrj.am

Vision 1.3.0 est **activé et enregistré depuis 22:32 UTC** sur
`https://vision.mrj.am/`. La [bascule nº 35541957332](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35541957332)
atteste la nouvelle génération après une nouvelle connexion SSH, six services
actifs, les deux timers de sauvegarde et 22 contrôles HTTP/TLS depuis le VPS,
puis 22 depuis le runner GitHub. La connexion web, CSRF, le refus anonyme,
la lecture PostgreSQL et la révocation de session ont réussi. Les identifiants
de sonde ont été retirés et les identifiants antérieurs conservés.

| Élément | Référence vérifiée le 20 septembre |
|---|---|
| Sources d'infrastructure installées | `d3699cd829bf996540a53085fe2c0539d9552ebc` |
| Sources Vision | `151ab64bd5c9c5c54297e88dbe4d548343cc4928` — version `1.3.0` |
| Répertoire installé | `/etc/nixos/vps-infrastructure/d3699cd829bf996540a53085fe2c0539d9552ebc` |
| Génération active et par défaut | `/nix/store/ppx3gxdx4rw36wah3wdz9lfdkl7z72ln-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Génération précédente protégée | `/nix/store/nndnndfac30p7rnwrxbk8sr6hljk5y5b-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Services actifs | `sshd`, `nginx`, `postgresql`, `matheval`, `vision`, `mrj-auth` |
| Sauvegardes quotidiennes actives | `postgresqlBackup-matheval.timer`, `postgresqlBackup-vision.timer` |
| Compte permanent | Activé le 21 septembre 2026 à 05:18 UTC ; accès API vérifié |

La [préparation nº 35541853819](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35541853819)
a contrôlé la génération, les invariants, les sauvegardes chiffrées des deux
bases et le retour complet de l'essai précédent. Nixpkgs, PostgreSQL, les
certificats et les paramètres de Matheval sont conservés. Le timer de retour
de cette bascule est désarmé après enregistrement ; les anciennes générations
et les preuves restent protégées. Aucun redémarrage du VPS n'a été effectué.

Lors de la bascule, le compte permanent n'était pas encore défini.
Le propriétaire a ensuite enregistré les deux secrets de compte dans
`vps-production`. Le [renouvellement nº 35564114945](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35564114945),
exécuté au commit `65cedea8e71c157aafdf341e6894d4185b5ed651`, a réussi le
21 septembre 2026 à 05:18 UTC : validation des secrets, installation du compte,
accès HTTPS authentifié à l'API et nettoyage des fichiers temporaires.
Le compte est commun au navigateur et à l'API générale ; le service de sessions
lit ce même fichier d'identifiants. Aucun secret n'est conservé dans ce rapport.
Les prochaines rotations suivent [VISION-WEB.md](VISION-WEB.md).
Le navigateur de la session Work reçoit encore une erreur 502 au 21 septembre ; le rendu
visuel n'a donc pas été vérifié depuis ce navigateur. Ce constat est distinct
des contrôles HTTP/TLS réussis sur le VPS et sur le runner GitHub.

La [CI d'infrastructure nº 35541763449](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35541763449)
et la [CI Vision nº 35540278729](https://github.com/MrJ-am/vision/actions/runs/35540278729)
ont réussi. Les fonctionnalités et les reprises des deux premiers essais
sont détaillées dans [VISION-WEB.md](VISION-WEB.md).

## Historique : migration du 18 septembre 2026

La migration de l'infrastructure est **activée et enregistrée depuis 21:10 UTC**.
Nginx, HTTPS, NixOS et PostgreSQL sont gérés par ce dépôt. Matheval conserve
son application, ses données, son schéma, ses publications et ses exports chiffrés.

## Références installées le 18 septembre

| Élément | Référence vérifiée |
|---|---|
| VPS | `187.77.95.158`, Hostinger `1982677` |
| Sources VPS installées | `fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb` |
| Commit opérateur de la bascule | `49d82f8167b8121fb03c7d95da02169bb6409e28` |
| Répertoire des sources | `/etc/nixos/vps-infrastructure/fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb` |
| Génération active et par défaut | `/nix/store/8cbhcffxr0xhybz2va6yz8rrxfgqgzy9-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Ancienne génération protégée | `/nix/store/5840x51nc7d2s7gw0zfyy6my47j6nh1i-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| Nixpkgs conservé | `/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos` |
| PostgreSQL | `17.11`, données `/var/lib/postgresql/17`, socket `/run/postgresql`, aucune écoute TCP |
| Matheval pendant la bascule | `d8d0f17f37f030d58c152d5e57ca2e2c5b5814ea` ; version de l'API `0.3.0` |
| Matheval après le relais | `841317fb87c8f81867ad884ca19ef93e8308838b` sur `master` |

`/etc/nixos/configuration.nix` importe la configuration de l'hôte dans le
répertoire des sources installé. Le module Matheval est la copie exacte du
commit amont `0bcdaf101cbdacb85694ca217fd21ab3f2eac828`, SHA-256
`8959538472392c6bff39cf91e3eeaa125b6814f0af15d63381258a51baf20086`.
Sa provenance figure dans `vendor/matheval/source.json`. Le patch historique
n'est plus à appliquer. Vision reste un exemple, sans service ni base activés.

## Contrôles et sauvegardes

- [Audit final nº 35396774874](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35396774874),
  commit `30decc1ab1deb39cd147dd289bd6a836e7a6c925`, réussi à 21:26 UTC après
  la publication de Mémoire : génération active et par défaut attendue,
  entrée NixOS persistante, retour désarmé, anciennes générations protégées,
  quatre services actifs, PostgreSQL et ses droits conformes, version applicative
  `841317fb87c8f81867ad884ca19ef93e8308838b` et onze contrôles HTTP/TLS réussis.
- [Préparation nº 35395032430](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395032430) :
  sauvegarde des sources et de la base, construction avec le Nixpkgs installé,
  comparaison des invariants, restauration isolée et retour ciblé des ACL testé
  deux fois. Seules les unités Matheval, PostgreSQL et son provisionnement
  changent ; Nginx, le réseau, SSH, le noyau et les certificats sont conservés.
- [Plan nº 35395215119](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395215119) :
  précontrôle exécuté depuis systemd avec l'environnement explicite, dry-run
  limité à PostgreSQL et Matheval, déclenchement du timer indépendant vérifié.
- [Bascule nº 35395320446](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395320446) :
  essai sous verrou de publication avec retour à quinze minutes, nouvelle
  connexion SSH, services actifs, onze contrôles HTTP/TLS et empreintes publiques
  identiques, refus anonymes 401, connexions SQL autorisées/refusées vérifiées.
  Les lignes antérieures et l'identité du stockage PostgreSQL sont conservées.
  La sauvegarde locale a été déclenchée puis restaurée dans une instance isolée ;
  l'export chiffré hors VPS a réussi. La même génération a ensuite été enregistrée
  pour le démarrage, et le timer a été désarmé après validation.
- [CI VPS nº 35395320531](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395320531) :
  vingt tests Python, syntaxe Nix, évaluations NixOS, isolation PostgreSQL 17 et
  restaurations dans un conteneur jetable réussis.

Les copies chiffrées de migration sont conservées trente jours dans les artefacts
[avant](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395032430/artifacts/10567635113)
et [après](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35395320446/artifacts/10567442831).
Les sauvegardes locales quotidiennes restent dans `/var/backup/postgresql`.
Le workflow Mémoire conserve son export chiffré quotidien et sa rétention de
quatorze jours ; la clé privée age reste hors du VPS et hors Git.

Le dossier privé `/root/vps-migrations/fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb/`
conserve `etc-nixos-before.tar`, `configuration.nix.before`, `rollback-acl.sql`,
les sauvegardes privées et `committed.json`. Les racines de GC sous
`/nix/var/nix/gcroots/vps-migrations/fa059d61acfc8cf5c5bd7f3f9c83600787f2c6eb/`
protègent l'ancienne génération, le candidat, Nixpkgs et Python.

Le retour autonome de l'essai est volontairement inopérant après enregistrement.
Un retour ultérieur doit faire l'objet d'une nouvelle opération VPS, après
examen des changements intervenus depuis. Ne pas restaurer un dump de production
pour revenir à une configuration ; le retour NixOS ne restaure pas les droits SQL.

Aucun redémarrage du VPS n'a été effectué. Le profil et le menu de démarrage
sont enregistrés ; le comportement après un redémarrage réel reste un contrôle
distinct à planifier dans une fenêtre appropriée.

## Relais Mémoire

Les consignes, le contrat et les références du serveur ont été actualisés au
commit `3896f94bd129a197c904c08e5544108b5c0a7c68`, dans la
[PR nº 8](https://github.com/MrJ-am/M-moire/pull/8). Elle inclut le déclenchement
du workflow de sauvegarde existant par `deploy/backup-request.json` sur `master`,
avec le compte `matheval-deploy` et les secrets existants. La
[CI de la PR](https://github.com/MrJ-am/M-moire/actions/runs/35395609673) a réussi,
dont quatorze tests API et trente-deux tests navigateur. La PR est fusionnée
sur `master`, commit `841317fb87c8f81867ad884ca19ef93e8308838b`.

La [sauvegarde Mémoire nº 35396161367](https://github.com/MrJ-am/M-moire/actions/runs/35396161367)
a réussi depuis `matheval-deploy` après la bascule, et son artefact chiffré
`matheval-backup-35396161367` est disponible jusqu'au 2 octobre 2026.
La [publication applicative](https://github.com/MrJ-am/M-moire/actions/runs/35396161100)
a réussi sur `master` : tests, déploiement avec `matheval-deploy` et comparaison
des fichiers servis avec le manifeste de la version vérifiée. L'intégration
de Mémoire est terminée ; ses publications ne reconstruisent pas NixOS.

## Accès et reprise de la tentative interrompue

Depuis ChatGPT Work, **toutes les opérations VPS passent par GitHub Actions**.
Work ne dispose pas de connexion SSH directe. L'environnement `vps-production`
contient la clé administrative existante, enregistrée avec l'autorisation du
propriétaire, et autorise uniquement la branche `main`, sans tag. Les workflows
applicatifs conservent leur compte de publication sans accès root général.

La première tentative [nº 35351617482](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35351617482)
a échoué avant l'activation : son service systemd ne recevait pas `NIX_PATH`.
Le retour a rétabli l'ancienne génération mais n'a pu lire le fichier SQL privé
sous le compte `postgres`. L'[audit de reprise](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35394636820)
a confirmé l'ancienne génération, les anciens droits, les quatre services actifs
et onze contrôles publics réussis. Aucune activation du candidat n'avait eu lieu.

Les corrections fixent l'environnement du service et font ouvrir le fichier
SQL par root avant de le transmettre à `psql`. La première reprise de l'unité
ancienne a constaté qu'elle avait été collectée par systemd ; une nouvelle unité
a exécuté le [retour complet nº 35394938751](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35394938751)
avec succès, droits SQL et contrôles publics compris. La nouvelle préparation
puis la bascule réussie ci-dessus utilisent un dossier distinct. Les preuves
de l'ancienne tentative restent conservées sous son identifiant `088d36c15f2f…`.
