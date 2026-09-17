# Transférer la configuration sans modifier le service rendu

**Procédure préparatoire, non exécutée.** Elle doit être concrétisée après
lecture du VPS réel par l'agent du projet VPS. Les commandes de construction
et de contrôle ci-dessous ne remplacent pas cet audit. Aucun script de ce
dossier ne lance automatiquement une activation.

## 1. Auditer et figer les sources

- Vérifier l'identité SSH avec `scripts/connect.sh` et ouvrir une seconde
  session. Confirmer que le terminal hPanel permet une récupération.
- Lire les consignes et les fichiers NixOS effectivement importés. Comparer
  leur contenu aux sources d'origine `d8d0f17` du mémoire : intégrer dans le
  candidat toute différence légitime. Ne pas écraser des réglages apparus
  depuis le relevé du 17 septembre.
- Exécuter `sh scripts/audit.sh` sur le VPS. Relever les services, les ports,
  les certificats, les sauvegardes et la version active de Matheval.
- Relever le chemin exact de `/run/current-system`, celui du profil système
  par défaut, et le résultat de `nix-instantiate --find-file nixpkgs`.
  Si les générations active et par défaut diffèrent, expliquer cette situation
  avant de poursuivre ; ne pas choisir aveuglément « la génération précédente ».
- Garder le canal et la source Nixpkgs déjà installés. Aucune commande
  `--upgrade`, `nix-channel --update` ni mise à jour du noyau pendant ce transfert.

Le nouvel agencement importe seulement `hosts/hostinger/configuration.nix`,
qui assemble le matériel, l'application et la passerelle. Le nom historique
du réseau `05-matheval-eth0` est conservé volontairement pour éviter de changer
l'identité d'un fichier réseau pendant la séparation.

## 2. Sauvegarder et construire à côté de l'installation

Créer un répertoire de migration privé, possédé par root, avec un identifiant
daté sous `/root/vps-migrations/`. Y conserver :

- une archive de `/etc/nixos/` et la copie exacte de son fichier d'entrée
  `configuration.nix`, y compris son éventuel lien symbolique ;
- les chemins des générations active et par défaut, avec une racine de GC
  explicite pour que la génération de retour reste disponible ;
- le commit de l'application active et un relevé des contrôles publics ;
- la référence à une sauvegarde de données récente et vérifiée, sans restaurer
  de base en production pour les besoins de cette migration.

Installer le dépôt candidat sous un chemin distinct, possédé par root, par
exemple `/etc/nixos/vps-infrastructure`. Ne pas encore modifier le fichier
d'entrée actif. Utiliser un commit identifié ; conserver tous les fichiers
de l'ancienne installation et la configuration candidate après la bascule.

Depuis le dépôt candidat, avec la source Nixpkgs précédemment relevée :

Python 3 est nécessaire aux contrôles. S'il n'est pas dans le PATH du VPS,
le fournir dans un shell temporaire `nix-shell -p python3`, avec `-I nixpkgs=...`
pointant vers la même source relevée, sans ajouter de paquet au système actif.

```sh
sh scripts/check.sh
nixos-rebuild build -I nixpkgs=/chemin/exact/deja-releve \
  -I nixos-config="$PWD/hosts/hostinger/configuration.nix"
```

Ne pas utiliser littéralement le chemin d'exemple. La construction produit
`result`, sans activer de services. Conserver le chemin résolu de ce candidat
et une racine de GC. Enregistrer le commit des sources qui l'a produit.

## 3. Comparer avant activation

Comparer l'ancienne configuration et la candidate :

- réseau, routes IPv4/IPv6, pare-feu SSH, clés root et déploiement ;
- démarrage, cloud-init et agent QEMU ;
- unités Matheval, PostgreSQL, sauvegardes et droits sudo ;
- paramètres, certificats, hôtes, redirections et emplacements Nginx ;
- chemins des données, fichiers de secrets et lien de publication active.

Le transfert initial conserve ces comportements. Seuls l'assemblage des
sources et leur responsabilité changent. Un redémarrage prévu de PostgreSQL,
de Matheval ou du réseau est un motif d'arrêt et d'explication.

Exécuter la commande `bin/switch-to-configuration dry-activate` **du candidat**
pour voir les unités affectées. Relever dans les unités générées le chemin du
binaire Nginx et celui de sa configuration candidate ; exécuter le contrôle
`nginx -t -c ...` correspondant à cette configuration complète. Un `nginx -t`
sur la configuration actuellement active ne valide pas le candidat.
Les certificats existants doivent être présents et leurs chemins inchangés.

La syntaxe Nix et l'évaluation du générateur ne prouvent pas, seules, que les
modules NixOS complets s'assemblent ni que la configuration Nginx fonctionne.

## 4. Préparer un vrai retour arrière

Avant la moindre activation, préparer dans le répertoire privé un script
root indépendant de la session SSH et du code candidat. Il doit restaurer :

1. le fichier d'entrée `/etc/nixos/configuration.nix` sauvegardé, avec ses
   attributs et son éventuel lien ;
2. le profil système par défaut vers le chemin enregistré, puis le menu de
   démarrage correspondant ;
3. la génération qui tournait avant le test, par son chemin exact.

En cas d'égalité des générations initiales, le chemin sauvegardé permet de
rétablir le profil via `nix-env --profile /nix/var/nix/profiles/system --set ...`
et d'activer directement son `bin/switch-to-configuration switch`.
Ce retour n'a besoin ni de GitHub, ni de reconstruire NixOS, ni d'un accès SSH.
Les bases et les fichiers applicatifs ne sont pas restaurés par ce script.

Programmer ce script avec un timer systemd, par exemple à dix minutes, avec
un nom propre à cette migration. Confirmer que le timer est armé **avant** le
test. Le script doit rester exécutable même si la nouvelle configuration casse
SSH ou Nginx. Un simple `trap` dans la session SSH est insuffisant.

Prévoir un verrou commun, tenu brièvement par le retour arrière et par
l'enregistrement final, pour éviter qu'ils s'exécutent en même temps. Ne pas
tenir ce verrou durant toute la phase d'essai : cela bloquerait le retour
programmé. Si le retour arrière a commencé, ne pas l'interrompre à mi-chemin.

## 5. Tester temporairement et contrôler

Coordonner une courte pause des publications. Le script `matheval-release`
utilise déjà `/srv/matheval/deploy.lock` ; détenir ce verrou durant la fenêtre
de comparaison empêche qu'une publication fausse le relevé. Le timer de retour
arrière ne doit pas attendre ce verrou. Le service continue à répondre.

Capturer le relevé HTTP avant le changement avec le registre installé. Pour
le transfert initial, `projects.json` décrit uniquement Matheval, donc convient.
Lors d'ajouts ultérieurs, utiliser une copie du registre précédent pour ce relevé.

Activer **le candidat déjà construit** avec son
`bin/switch-to-configuration test`. Cette action ne doit pas changer le profil
de démarrage par défaut. Ne pas relancer une reconstruction différente au
moment du test. Le timer reste armé.

Vérifier ensuite :

- une **nouvelle** connexion SSH avec vérification de la clé d'hôte ;
- `systemctl is-active sshd nginx postgresql matheval`, puis les autres services ;
- la santé locale de l'API et le même commit dans `/srv/matheval/current/RELEASE` ;
- `python3 scripts/probe.py --baseline /chemin/prive/avant.json` depuis un accès
  public fonctionnel, avec le registre candidat ;
- les temporisations ACME, les certificats, les sauvegardes et les journaux
  d'erreurs nécessaires, sans afficher les secrets ni les réponses collectées.

Ce contrôle inclut HTTPS, HTTP→HTTPS, www, les deux redirections 308, le
questionnaire, l'administration, le JavaScript principal, la santé JSON, et
les refus 401 pour l'administration et les statistiques anonymes. Il compare
aussi les empreintes des fichiers marqués stables. Aucun questionnaire fictif
ne doit être rempli et aucune base de test ne doit remplacer la production.

Une erreur laisse le retour programmé agir, ou déclenche explicitement le
script de restauration. Ne pas enregistrer une configuration partiellement valide.

## 6. Enregistrer exactement la génération testée

Après réussite de tous les contrôles, sous le verrou d'enregistrement :

- vérifier que le retour arrière n'a pas démarré et que la génération candidate
  est toujours celle qui tourne ;
- remplacer atomiquement le fichier d'entrée NixOS par un import du chemin
  stable de ce dépôt, en conservant sa sauvegarde ;
- positionner le profil par défaut sur **le même chemin candidat**, puis
  exécuter `bin/switch-to-configuration boot` de ce candidat pour enregistrer
  son démarrage, sans reconstruire une variante ;
- vérifier le profil, l'entrée de configuration et les services une dernière fois ;
- annuler le timer seulement lorsque l'enregistrement et les contrôles ont réussi.

À toute erreur d'enregistrement, restaurer immédiatement l'état sauvegardé.
Conserver l'ancienne génération et les sources de retour. Aucun redémarrage
du VPS n'est requis pour ce transfert ; le comportement après redémarrage
restera un contrôle distinct, à prévoir dans une fenêtre appropriée.

## 7. Fermer le relais côté mémoire

Renseigner `docs/ETAT.md` et `deploy/INFRASTRUCTURE.org` du mémoire : URL du
dépôt d'infrastructure, commits, génération, date des contrôles et sauvegarde
de retour. Faire passer la PR nº 8 en revue puis l'intégrer selon le workflow
du propriétaire. Vérifier sa publication applicative et ses sauvegardes.

Le projet mémoire doit alors continuer à publier uniquement l'application.
Toute évolution du module applicatif se transmet à ce dépôt par une mise à
jour explicite de la copie revue ; la publication courante ne contrôle jamais
Nginx, les domaines ou le système.

Références : [NixOS — changements de configuration](https://nixos.org/manual/nixos/stable/#sec-changing-config)
et [Nginx — rechargement et validation](https://nginx.org/en/docs/control.html).
