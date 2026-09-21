# Préparer Apprendre à démontrer sur le VPS

## Cible et état

La cible retenue par le propriétaire est **https://logique.echos.systems** sur
le VPS NixOS `187.77.95.158`. Les indications antérieures sur ChatGPT Sites
dans la documentation applicative ne décrivent plus la cible souhaitée.
La préparation se trouve sur `preparation/logique-vps`.

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
| Application | `52a3d4b7714608e09561728508818525b53aacda` |
| Style | `492afe54cba22ed49c35423d4f37dae1ba0d9944` |
| Signature | `17495b13cefa24473e37434b98336b27caec8cdf` |
| Exécution applicative réussie | `35627133194` |
| Artefact `apprendre-a-demontrer-preparation` | `10652278750` |
| SHA-256 ZIP | `5d2d267fd520729180b08942cec30293608bb1da6a1ef4c4c78794858bfedc0a` |
| Expiration annoncée par GitHub | 28 septembre 2026, 16:41 UTC |

L'archive a été téléchargée et vérifiée pendant la reprise : empreinte ZIP
identique, révisions cohérentes et 75 fichiers `dist` vérifiés, manifeste inclus.
Le vérificateur refuse les fichiers supplémentaires, les empreintes fausses,
les liens et les chemins sortant du répertoire. Il peut extraire dans un
répertoire neuf, jamais dans une publication active :

```sh
python3 scripts/logique_artefact.py /chemin/artefact.zip --extraire /chemin/neuf
```

Son manifeste conserve `typographieValidee: false`,
`hebergementConfirme: false`, `publicationAutorisee: false`.
Ne pas modifier ces indicateurs dans le ZIP pour le rendre publiable :
achever les validations dans l'application et produire les artefacts coordonnés.
Cette archive reste une référence de préparation ; ne pas la conserver
uniquement derrière un lien temporaire si la bascule a lieu après son expiration.

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
La génération complète n'a pas encore été construite sur le VPS.

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
4. Valider la typographie, les droits d'intégration Vimeo pour ce domaine,
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

La publication coordonnée et la validation typographique restent des conditions
de l'utilisateur et du contrat du style ; la disponibilité de Logique ne doit
pas être annoncée avant leur réalisation et les contrôles de production.
