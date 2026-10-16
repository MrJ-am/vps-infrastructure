# Forgejo privé — intégration déclarative

Candidat de la mission Forgejo du 16 octobre 2026. Le VPS inspecté utilise
`/etc/nixos/configuration.nix`, sans flake. L’intégration conserve cette entrée
et toute sa chaîne d’imports ; elle ne migre pas les applications existantes.

## Sources et versions

`module.nix` utilise le module NixOS `services.forgejo`. `integration.nix`
importe la configuration active sauvegardée et ajoute uniquement une règle
peer `local forgejo forgejo`. PostgreSQL 17, socket, ident map et autres règles
restent identiques. Nginx ajoute un hôte, ACME utilise l’infrastructure existante.
HTTP applicatif : boucle locale 3004 ; Git SSH intégré : 2222 ; SSH administratif :
22 inchangé. Actions, runners, inscriptions publiques et dépôts publics désactivés.

`versions.json` verrouille Nixpkgs, Forgejo, Pandoc, MathJax et ses polices.
`assets.nix` vérifie les archives par SHA-256. Aucune dépendance CDN ou installation
npm à l’activation. Une mise à jour de Forgejo/Pandoc exige la requalification puis
la modification du verrou ; les assertions empêchent une mise à jour implicite.

## Org, assainissement et MathJax

`markup.orgmode` remplace explicitement le moteur natif. Dans Forgejo 16.0.3,
les moteurs natifs sont enregistrés à l’initialisation des paquets ; les externes
le sont ensuite dans `routers/init.go`. `RegisterRenderer` remplace les entrées
par nom et extension. Ce comportement est également exercé dans le navigateur,
avec un README et trois fichiers ordinaires de sous-répertoire.

Pandoc reçoit stdin avec `--sandbox --from=org --to=html5 --mathjax`. Temps et
mémoire sont bornés ; aucune inclusion de fichiers serveur n’est autorisée.
`NEED_POSTPROCESS=true` conserve le traitement Forgejo des liens et images.
L’assainissement reste activé : une règle propre au renderer permet uniquement
les classes `math inline` et `math display` sur les spans. Aucun script, gestionnaire
d’événement ou URL JavaScript n’est autorisé par cette règle.

Le point d’extension officiel `custom/footer` charge le JavaScript de confiance ;
aucun template interne n’est remplacé. MathJax se charge seulement en présence
préalable de spans mathématiques produits par le renderer et compose ces spans.
CHTML, AMS, numéros/références, extension safe et polices locales ; pas de paquet
TeX `require`/HTML ou chargement de paquets arbitraires. Les grandes expressions
restent accessibles par défilement horizontal dans leur conteneur, sans élargir
la page mobile. Le lecteur Org Pandoc 3.7.0.2 reconnaît les quatre délimiteurs
exercés dans `fixtures/docs/delimiteurs.org` ainsi que les environnements align.

## Préparation et activation

Le circuit existant `.github/workflows/monolithe-deploiement.yml` porte les
opérations fermées `forgejo-diagnostic`, `forgejo-preparer`, `forgejo-deployer`
et `forgejo-retour`. Aucun workflow ou runner supplémentaire. Le descripteur
`operations/forgejo-candidat.json` identifie le commit des sources à transporter.

La préparation compare l’évaluation de base à la génération active puis les
unités protégées, hôtes existants, SSH, réseau, noyau, PostgreSQL et sauvegardes.
Elle construit le système sans activation et conserve une racine GC.
Le déploiement vérifie la résolution publique exacte A=187.77.95.158 et l’absence
d’AAAA non qualifié. Un DNS absent arrête l’activation. Il réutilise le mécanisme
central de sauvegarde/restauration isolée avec la génération actuelle vérifiée,
puis arme un retour indépendant de dix minutes avant de changer la génération.
Les données courantes ne sont jamais restaurées lors d’un retour du code.

```sh
gh workflow run monolithe-deploiement.yml --repo MrJ-am/vps-infrastructure --ref main -f operation=forgejo-preparer
gh workflow run monolithe-deploiement.yml --repo MrJ-am/vps-infrastructure --ref main -f operation=forgejo-deployer
```

Le journal de construction/activation détaillé reste privé sur le VPS dans
`/root/mrjam-corrections/forgejo/<revision>/`. Un arrêt doit être analysé avant
nouvelle tentative. L’ajout d’un chemin HBA peut imposer un redémarrage PostgreSQL
borné ; le dataDir et la version majeure ne changent pas. Les autres processus
protégés doivent conserver leur PID.

## Premier administrateur

Au premier démarrage seulement, si aucun compte n’existe, le service
`forgejo-bootstrap` crée `mrjam-admin`. Forgejo génère lui-même un mot de passe
aléatoire de 40 caractères, absent des arguments, du store et des journaux.
Le résultat est conservé dans `/var/lib/forgejo-bootstrap/initial-admin.txt`,
accessible uniquement à root. Le propriétaire peut le consulter dans son canal
administratif habituel ou le terminal hPanel, se connecter sur HTTPS et changer
le mot de passe à la première connexion. Supprimer ensuite ce fichier initial.
Configurer la double authentification et enregistrer la clé SSH personnelle.
Aucun secret de connexion n’est publié par l’opérateur GitHub.

## Sauvegardes et restauration

Le timer quotidien `forgejo-backup` (04:45 UTC, décalage aléatoire maximal dix
minutes) suspend brièvement Forgejo pour obtenir une copie cohérente des dépôts,
données, configuration/secrets runtime et base PostgreSQL. Le service reprend
l’instance même si la sauvegarde échoue. Les archives sont dans
`/var/backup/forgejo`, root uniquement, rétention tmpfiles de 30 jours.

Chaque paire comprend `*.tar.age` et `*.tar.age.key.age`. La clé éphémère de
l’archive est enveloppée pour le destinataire age déjà configuré en production.
Le service vérifie le déchiffrement, la comparaison des deux fichiers et la
lecture du catalogue pg_restore avant de publier la paire. La clé claire et les
copies temporaires sont effacées ; aucune clé n’entre dans le store.

Pour restaurer, déchiffrer d’abord le fichier de clé avec l’identité age personnelle,
puis l’archive avec cette clé ; extraire `forgejo.dump` et `data.tar` dans un
répertoire privé. Restaurer d’abord dans une instance PostgreSQL et un état
Forgejo isolés, avec la même version du programme. Une restauration en production
requiert l’arrêt Forgejo et la préservation explicite des écritures plus récentes.
Les archives locales doivent suivre la copie hors VPS déjà utilisée ; aucun
stockage distant n’est inventé par cette intégration.

## Validation

`scripts/forgejo-navigateur.py` teste une instance réelle avec Chromium, un compte
et dépôt privés explicitement fournis ; huit vues à 1280 et 390 px. Il exige des
nœuds CHTML et des fractions/matrices réellement composées, pas seulement du TeX,
et refuse erreurs JS, ressources manquantes, CDN, injections et page débordante.
`scripts/forgejo-git.py` exerce clone/push HTTP(S) et SSH avec une clé temporaire
puis retirée. Aucun mot de passe ne figure dans la ligne de commande ou les preuves.
Ces scripts sont manuels et ne déclenchent pas de tests au push.

Les preuves locales et distantes restent distinctes. Une instance locale SQLite
ne qualifie pas la connexion PostgreSQL, ACME, le pare-feu ou la persistance du VPS.
L’absence de DNS bloque les essais de production et doit rester visible dans le
compte rendu. Le redémarrage d’un service ne prouve pas un redémarrage complet du VPS.
