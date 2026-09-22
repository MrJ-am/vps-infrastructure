# Apprendre à démontrer — site publié

Le site est publié depuis le 22 septembre 2026 à 11:13 UTC sur
[logique.echos.systems](https://logique.echos.systems/?accueil=1).
L'[activation 35720088997](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35720088997)
a vérifié le certificat réel, toutes les ressources, quatre formats d'écran,
la récupération des anciennes redirections `/matheval/` et les cinq lecteurs Vimeo.
Les hôtes inconnus sont désormais refusés. Les autres sites et l'authentification
Vision ont passé leurs contrôles ; la génération testée est enregistrée.

Le code servi est `615439c841db1934ffaddc1dee64c85ff6c56cf2`, style
`b2177c0fd2c46c6f528266d30f7b933d3add1566`, identité
`17495b13cefa24473e37434b98336b27caec8cdf`. Son intégration sur le main
applicatif est `6a0c76340d0c2132b80d002af3b13d9f35b78cef`, au même arbre Git.
Lire [la procédure et ses preuves](CORRECTIONS-SITES-20260922.md),
[l'état courant](ETAT.md) et `operations/corrections-publication.json`.
Les anciennes préparations ci-dessous sont conservées comme historique ;
elles ne doivent pas être rejouées après cette activation.

## Historique de la préparation initiale


## Cible et état

La cible retenue par le propriétaire est **https://logique.echos.systems** sur
le VPS NixOS `187.77.95.158`. Les indications antérieures sur ChatGPT Sites
dans la documentation applicative ne décrivent plus la cible souhaitée.
La préparation a été intégrée sur `main` depuis `preparation/logique-vps`.

Le site est statique : Nginx lit `/srv/logique/current`, sans nouveau backend,
port local, compte SQL ou base. Les routes pédagogiques utilisent `#/…` ;
elles restent à la racine HTTP. Une ressource absente répond 404, sans renvoyer
le HTML à la place de JavaScript. Les noms de fichiers n'étant pas hachés,
`Cache-Control: no-cache` oblige leur revalidation. KaTeX, vidéos et ports Elm
restent ceux de l'artefact testé.

**Rien n'est activé par ce lot.** `projects.json` et le point d'entrée
`hosts/hostinger/configuration.nix` conservent les projets actuellement servis.
Le module Logique et les deux points d'entrée candidats sont explicites.
Le workflow de préparation est réservé à `main` et à `vps-production`.
Il se lance manuellement ou par une demande explicite dans
`operations/logique-preparation.json`, après intégration revue de la branche.
Cette demande n'accepte que l'opération `prepare`, une révision exacte déjà
intégrée et sa CI réussie. Sa présence n'atteste pas son exécution.

## Références et preuve de départ

L'[audit Actions 35637628338](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35637628338),
commit `ba66dfcf939f299f9a296658aeaab938366b719e`, a réussi le 21 septembre 2026
à 18:19 UTC : 22 contrôles publics HTTP/TLS, droits PostgreSQL, sauvegardes,
générations et seconde connexion depuis le runner.
Le DNS avait exactement l'enregistrement A attendu, sans AAAA ni CNAME.
Le certificat était absent, ainsi que la publication au chemin alors envisagé
`/srv/apprendre-a-demontrer/current`. Le précontrôle actualisé vérifie aussi
`/srv/logique/current`, chemin du candidat.

`operations/logique-etat-attendu.json` conserve les références de cet audit :
génération active et de démarrage, Nixpkgs, entrée NixOS et publications
Matheval/Vision. La préparation refuse une dérive ; refaire l'audit puis
revoir les préconditions si une autre publication intervient.

| Élément | Référence figée |
|---|---|
| Application | `7a356ca3ec3682c95aa841c968822c24dc683dbe` |
| Style | `492afe54cba22ed49c35423d4f37dae1ba0d9944` |
| Signature | `17495b13cefa24473e37434b98336b27caec8cdf` |
| Exécution applicative réussie | `35661154380` |
| Artefact `apprendre-a-demontrer-preparation` | `10667157261` |
| SHA-256 ZIP | `e07b6c68813d1b679e00b4bf9c82f7929504839b1fda3181a65a5c8e10111c55` |
| Expiration annoncée par GitHub | 28 septembre 2026, 22:10 UTC |

L'archive a été téléchargée et vérifiée pendant la reprise : empreinte ZIP
identique, révisions cohérentes et 75 fichiers `dist` vérifiés, manifeste inclus.
Ses 74 ressources restent identiques à l'archive initiale `10652278750` ;
seule la référence applicative du manifeste évolue.
Le vérificateur refuse les fichiers supplémentaires, les empreintes fausses,
les liens et les chemins sortant du répertoire. Il peut extraire dans un
répertoire neuf, jamais dans une publication active :

```sh
python3 scripts/logique_artefact.py /chemin/artefact.zip --extraire /chemin/neuf
```

Son manifeste conserve `typographieValidee: false`,
`hebergementConfirme: false`, `publicationAutorisee: false`.
Ne pas modifier ces indicateurs dans le ZIP pour le rendre publiable :
produire et contrôler les candidats complets dans le mécanisme coordonné.
Cette archive reste une référence de préparation ; ne pas la conserver
uniquement derrière un lien temporaire si la bascule a lieu après son expiration.

## Typographie complète validée en atelier privé

Signature est un dépôt privé. La CI publique de l'application conserve les
tests fonctionnels ; les ressources d'identité complètes sont contrôlées par
le [workflow privé nº 35661307369](https://github.com/MrJ-am/Signature/actions/runs/35661307369),
réussi sur l'application `7a356ca3ec3682c95aa841c968822c24dc683dbe`.
Le commit opérateur Signature est `04e2402ed5fc599d759e95824ba16a852c4241ec`,
sur `validation/logique-typographie`. Les sources d'identité restent à la
révision originale `17495b13cefa24473e37434b98336b27caec8cdf`.

Le workflow recompile l'application, vérifie 190 cas du correcteur, 299 formules
KaTeX, les 58 exercices, les 12 bilans et les pages vidéo simulées, puis charge
les deux fontes originales et leur licence dans `.cache/site-complet`.
Les huit contextes HTTP (racine et préfixe, largeurs 320, 390, 768 et 1280)
valident les empreintes servies, les dimensions originales, la sélection et
le copier-coller natif des six caractères de `MrJ.am`, point U+002E compris.
Les captures à 320 et 1280 pixels ont été examinées.

Le rapport complet et ses empreintes sont conservés dans
`operations/logique-typographie.json`. Son artefact privé `10666862486` a été
téléchargé et vérifié, ainsi que ses 75 fichiers `dist`. Le candidat complet
ajoute uniquement les deux fontes et leur licence à ces ressources.
L'archive de préparation exclut les fontes ; le rapport typographique y figure,
mais son `dist` reste incomplet et non publiable. Aucune clé inter-dépôts ni
accès VPS n'a été ajouté à cet atelier. La publication privée collective doit
recomposer, contrôler puis conserver exactement le candidat complet à servir.

## Les deux générations candidates

1. `hosts/hostinger/logique-acme.nix` ouvre seulement le défi ACME géré par
   NixOS sur HTTP. Le reste du nouvel hôte répond 404 ; il n'exige pas encore
   le certificat Logique et ne sert pas l'application.
2. `hosts/hostinger/logique.nix` sert les fichiers et force HTTPS.
   Son `nginx -t` exige le certificat Logique réel. Une vérification avec
   un certificat de substitution ne permet pas d'autoriser cette phase.

`tests/logique.nix` évalue les deux systèmes complets avec le Nixpkgs de CI
et compare services, sites précédents, réseau, clés et sauvegardes.
Les tests Nginx exécutent les locations générées et vérifient les fichiers,
types MIME, règles de cache, absences et fichiers cachés.
Ils ne prouvent ni l'émission ACME ni l'état actuel du VPS.

La [CI nº 35656506154](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35656506154)
valide ce lot au commit `b722165485e9b3b325b150f05ae7da5919a57984` :
55 tests, routage Nginx réel, évaluations des systèmes ACME/HTTPS,
comparaison des invariants et tests PostgreSQL 17 avec restaurations isolées.
Les générations complètes ont ensuite été construites sur le VPS.

## Construction attestée le 21 septembre à 21:57 UTC

L'[exécution nº 35659924636](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35659924636)
a réussi au commit opérateur `d659dde6034056dac2be73519804ce2ee33cb436`,
sur les sources figées `e9a4ed68fa71a072ff0815d28e7e3ffd3e9517ae`.
Le rapport complet figure dans `operations/logique-construction.json`.

| Candidat construit | Génération NixOS |
|---|---|
| ACME, test Nginx réussi | `/nix/store/wvh5hif7p6z5b8cvlyf4pmp96n2fnmq9-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |
| HTTPS, test Nginx en attente du certificat | `/nix/store/91jr4718xb1m0mbybzfbj14wa9p3dncr-nixos-system-nixos-26.05.8639.c5c4a43b0e80` |

Les 22 contrôles HTTP/TLS réussissent avant et après la construction.
Le relevé final à 21:57:12 UTC conserve la génération active et de démarrage
`ppx3gxdx4rw36wah3wdz9lfdkl7z72ln-…`, l'entrée NixOS et les versions
Matheval/Vision. Les six services et les deux timers sont actifs ; aucun
certificat ni lien de publication Logique n'est apparu.
Le script de retour n'a pas été armé ni exécuté. La demande est consommée :
ne pas relancer la même révision, dont les preuves sont conservées.

L'artefact de rapport est `10667611152`, SHA-256 ZIP
`e7a81a089c99d6baf5bc29bc0eb7ab7ce9db8aa12a340f97d26981bce0d6b306`.

## Construction sur le VPS, sans activation

Après intégration de cette branche, lancer **Préparer les générations Logique
sans activer**, sur `main`, manuellement ou en modifiant la demande dédiée.
Le champ `revision` désigne les sources testées, indépendamment du commit
qui déclenche le workflow. Le runner exige une CI `check.yml` réussie sur
cette révision, vérifie qu'elle appartient à l'historique intégré, puis
archive exclusivement ces sources. Une tentative déjà engagée n'est pas écrasée.
Le runner utilise exclusivement `scripts/connect.sh` et `vps-production`.
Il vérifie le DNS, les sites existants et les préconditions, conserve
`/etc/nixos` dans un dossier privé, puis construit les deux générations avec
le Nixpkgs déjà installé. Il compare les invariants à la génération active.
Il protège les générations avec des racines de GC et teste la configuration
Nginx d'amorçage avec les certificats existants.

Les sources candidates restent sous `/etc/nixos/vps-infrastructure/<commit>/`.
Le rapport, les sauvegardes et le script de retour restent sous
`/root/logique-preparations/<commit>/`. Aucun fichier d'entrée actif, profil,
service, certificat ou lien `current` n'est changé par ce workflow.
Le script de retour système est généré et sa syntaxe vérifiée ; son timer
n'est pas encore armé. HTTPS reste explicitement non testé sans son certificat.
La construction se termine par une nouvelle connexion du runner et les
contrôles HTTP/TLS comparés au relevé initial.

## Activation distincte et coordonnée

Le présent lot ne fournit pas de workflow d'activation. Les étapes suivantes
restent à préparer et à exécuter dans le mécanisme collectif :

1. Vérifier le rapport de construction, le nouvel audit et les sauvegardes.
   Relire les unités affectées ; arrêter en cas de changement d'un service,
   droit SQL, réseau ou domaine sans rapport avec Logique.
2. Tester le déclenchement indépendant du retour, puis armer son timer avant
   l'essai de la génération ACME. Conserver la génération initiale et les
   fichiers de retour ; ne pas réutiliser les scripts des anciennes migrations.
   La phase ACME est elle-même une activation système, à autoriser séparément.
3. Vérifier les sites précédents et l'émission du vrai certificat
   `logique.echos.systems`. En cas d'échec, rétablir la génération initiale,
   son entrée et son profil par le retour indépendant. Ne pas effacer les
   certificats antérieurs ni restaurer une base.
4. Refaire les contrôles du candidat complet, vérifier les droits Vimeo pour ce domaine,
   les tests applicatifs et le manifeste privé collectif de Mémoire, Vision
   et Logique. Fixer les autorisations inter-dépôts sans réutiliser
   arbitrairement une clé ou un secret d'un autre projet.
5. Préparer les mêmes artefacts déjà testés dans des répertoires de versions
   distincts, appartenant à root et lisibles par Nginx. Le futur mécanisme
   de publication applicative doit disposer de droits limités à Logique.
   Réserver le lien `current`, vérifier les empreintes et tester
   **la configuration HTTPS exacte** avec le nouveau certificat.
6. Armer le retour collectif avant la bascule. Pour Logique, qui n'a pas de
   publication préalable, le retour retire seulement le lien de cette
   tentative et restaure le système initial. Pour les autres projets,
   rétablir leurs anciens artefacts sans toucher aux données collectées.
   Conserver toutes les versions et les preuves.
7. Après bascule, vérifier depuis le VPS et le runner les anciens sites,
   leurs refus anonymes, le nouveau HTTPS, chaque fichier servi contre son
   empreinte, les parcours, KaTeX, les vidéos réelles et une nouvelle connexion.
   Utiliser le registre courant complété par `operations/logique-site.json`.
   La comparaison collective tient compte des changements d'interface
   autorisés ; le relevé « fichiers inchangés » de la préparation ne suffit pas.
8. Enregistrer exactement les générations et artefacts testés sous verrou,
   puis désarmer les retours après réussite complète. Mettre à jour l'état
   attesté avec les URLs des exécutions. Aucun succès de CI n'est un déploiement.

La typographie est validée pour la révision applicative ci-dessus. La publication
coordonnée reste une condition de l'utilisateur et du contrat du style ; la
disponibilité de Logique attend cette bascule et les contrôles de production.
