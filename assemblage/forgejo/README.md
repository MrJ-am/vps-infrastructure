# Forgejo privé — intégration déclarative

Intégration de la mission Forgejo du 16 octobre 2026, domaine `forge.mrj.am`. Le VPS inspecté utilise
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
`NEED_POSTPROCESS=true` conserve le traitement Forgejo des images. Le filtre
versionné `org-links.lua` résout les liens relatifs avec `GITEA_PREFIX_SRC`, y
compris pour les README intégrés ; les sources restent utilisables dans Emacs.
Voir [LIENS-ORG.md](LIENS-ORG.md) pour la cause et les contrôles de navigation.
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
et `forgejo-retour`, puis `forgejo-tester` et `forgejo-persistance`. Aucun workflow ou runner supplémentaire. Le descripteur
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
borné ; le dataDir et la version majeure ne changent pas. Seules ses dépendances explicites peuvent également redémarrer, avec le même code ;
les autres processus protégés doivent conserver leur PID.

## Connexion et administration actuelles

La seule connexion Web est **Kanidm**, via `log.mrj.am`. Le compte administrateur
existant est renommé **MrJam** et rattaché à l'UUID de l'identité propriétaire
native. L'ancien fichier de mot de passe initial est supprimé ; aucun formulaire
ou compte local de secours n'est proposé. La réparation reste possible par le
canal root/Nix existant. Les clés et jetons restent les moyens techniques Git/API.

Le guide [SSO-QUOTAS.md](SSO-QUOTAS.md) décrit la connexion, les limites natives,
le nombre de dépôts par compte dans l'administration, les quotas de stockage par
API et l'outil `scripts/forgejo-quotas.py`. Les défauts initiaux sont illimités
(`-1`), avec moteur de quotas activé ; aucun chiffre arbitraire n'est imposé.

## Sauvegardes et restauration

Le timer quotidien `forgejo-backup` (04:45 UTC, décalage aléatoire maximal dix
minutes) suspend brièvement Forgejo pour obtenir une copie cohérente des dépôts,
données, configuration/secrets runtime, état OIDC `forgejo-identity` et base PostgreSQL. Le service reprend
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
Aucune copie hors VPS n’est configurée par cette intégration ; le transport
externe reste à raccorder si une destination de sauvegarde existe.

## Validation

`scripts/forgejo-navigateur.py` teste une instance réelle avec Chromium, un compte
et dépôt privés explicitement fournis ; huit vues à 1280 et 390 px. Il exige des
nœuds CHTML et des fractions/matrices réellement composées, pas seulement du TeX,
et refuse erreurs JS, ressources manquantes, CDN, injections et page débordante.
`scripts/forgejo-git.py` exerce clone/push HTTP(S) et SSH avec une clé temporaire
puis retirée. Aucun mot de passe ne figure dans la ligne de commande ou les preuves.
Ces scripts sont manuels et ne déclenchent pas de tests au push.
`tests/forgejo-integration.nix`, évalué avec Nixpkgs verrouillé, reproduit la
priorité PostgreSQL 20, vérifie son extension exacte et le maintien du timer ACME.
La dérivation `nginxConfigDrv` du résultat doit aussi être construite : Gixy
contrôle alors les en-têtes réellement générés, dont l’héritage sur les ressources
MathJax. Aucun contrôle de sécurité du constructeur NixOS n’est désactivé.

Les preuves locales et distantes restent distinctes. Une instance locale SQLite
ne qualifie pas la connexion PostgreSQL, ACME, le pare-feu ou la persistance du VPS.
Le DNS est contrôlé avant activation. Le redémarrage d’un service ne prouve pas un redémarrage complet du VPS.


## Validation de production actuelle

`forgejo-tester` utilise un jeton d'exploitation temporaire créé par la CLI native
pour `MrJam`, compte administrateur rattaché à Kanidm. Il crée le dépôt privé
`MrJam/org-validation`, vérifie l'API de gestion des quotas et exerce Git HTTPS/SSH
avec une clé temporaire. Le jeton est capturé uniquement par l'opérateur SSH et
révoqué dans son `finally` ; aucun secret ni jeton chiffré réutilisable n'est publié.
Le dépôt historique `forgejo-validation/org-validation` reste conservé ; son
ancien compte de validation local est bloqué, sans suppression de données.

`forgejo-persistance` redémarre uniquement Forgejo, compare le commit et les PID
protégés, puis lance la sauvegarde avec restauration PostgreSQL isolée, empreintes
de toutes les tables et `git fsck` des dépôts. Le cluster et les copies claires sont
supprimés à la fin ; un verrou commun empêche la concurrence entre les sauvegardes.

`scripts/forgejo-sso-navigateur.py` vérifie en production l'absence de formulaire,
les refus POST/Basic, l'unique fournisseur, le client/retour OIDC et PKCE vers le
vrai Log. `scripts/forgejo-sso-qualifier.py` exerce les programmes natifs en isolation,
avec vraie authentification MFA et échange OIDC, création externe, renommage et
quotas. La connexion personnelle MFA de production reste réservée au propriétaire.
Les qualifications historiques Org/CHTML restent dans `qualification-production.json` ;
le nouveau reçu SSO est `qualification-sso-production.json`.

## État installé et maintenance

État effectif et reçus : `COMPTE-RENDU.md`, `qualification-sso-production.json`.
Le déploiement SSO autorise uniquement les changements d'unités Forgejo requis
pour l'identité, le compte et sa sauvegarde. PostgreSQL, Kanidm, les autres unités
protégées, Nginx et les hôtes existants restent identiques.

Ne pas supprimer `/root/mrjam-corrections/forgejo/` : les configurations de base,
imports et racines de retour y sont préservés, comme dans le circuit existant.
Sauvegarder cette chaîne avec `/etc/nixos` et le dépôt Infrastructure.
Avant une future promotion, réinspecter la génération/configuration active et
actualiser les préconditions strictes de `promouvoir.py` ; elles empêchent la
réapplication aveugle sur une configuration modifiée. Les sources initiales et
les corrections restent dans l'historique Git, avec leurs descripteurs exacts.
