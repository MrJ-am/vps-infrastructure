# Promotion du candidat qualifié localement

Les sources Style effectivement consommées à chaque verrou sont incluses dans
le bundle privé de qualification, séparées de sa tête courante. Le préparateur
vérifie le verrou, ses fichiers et les entrées du reçu sur cette révision, sans
fetch distant ni copie divergente maintenue dans un dépôt. La preuve historique
MCP et sa trace sont vérifiées hors ligne : aucune nouvelle condition synthétique
ni connexion actuelle n'est prétendue. Les contrôles Python de routage sont
qualifiés séparément ; ces outils restent hors du graphe produit.

Le développement et les campagnes de qualification se font dans Codex. Le
workflow `monolithe-deploiement.yml` vérifie la soumission, prépare le système,
qualifie une restauration récente, active et sonde le VPS. Aucun déclenchement
au push, aucune reconstruction du binaire ni campagne unitaire sur le runner.

Les reçus restent `locale-non-attestee`, `autorise_publication: false`. Leur
présence seule ne permet aucune publication. La chaîne de confiance retenue est
une soumission de l'atelier autorisé par la mission, publiée avec le credential
du propriétaire dans son dépôt d'infrastructure :

1. `monolithe-candidat.py` exige sources commitées, les six révisions verrouillées,
   tous les reçus réussis avec les empreintes actuelles et le même binaire Nix.
   L'archive contient les sources exactes, ressources, reçus et export NAR de ses
   deux sorties propres. Les chemins des dépendances officielles sont verrouillés
   et substitués par Nix avec le cache signé déjà utilisé par le VPS. L'image a été construite séparément de l'image de développement.
2. L'archive est chiffrée par age officiel vers la clé publique SSH du VPS déjà
   verrouillée dans `scripts/ssh-known-hosts`. Seul `candidat.tar.gz.age` est
   transportable sur GitHub ; aucun source privé ou binaire en clair dans
   le dépôt public ou les artefacts Actions. Aucun credential supplémentaire.
3. Le descripteur `operations/monolithe-candidat.json`, commité sur main, verrouille
   l'asset numérique et son producteur GitHub MrJ-am/id12571490 ou, lorsque cet
   endpoint n'est pas accessible, le commit exact d'une branche d'artefact isolée
   du même dépôt et le chemin `candidat.tar.gz.age` ou ses parties numérotées
   dans l’ordre ; aucun chemin libre. La branche contient seulement le chiffré
   et ses métadonnées publiques. Il verrouille les octets,
   les empreintes du chiffré, de l'archive, du manifeste interne et du binaire.
   `soumission_autorisee_par_proprietaire` consigne l'autorisation de cette
   mission ; ce n'est pas une signature ni une confirmation personnelle nouvelle.
4. La promotion est un dispatch central par MrJ-am, sur main, dans l'environnement
   existant `vps-production`. SSH est celui de `docs/ACCES.md`. Le VPS compare sa
   clé publique avant de déchiffrer ; sa clé privée reste exclusivement sur le VPS.
   Extraction bornée sans liens, contrôle des fichiers, import du même NAR.
5. Le préparateur vérifie graphe Lisp, recettes et entrées de chaque reçu,
   image, manifeste, ressources et invariants Nix réels. L'environnement local
   décrit dans les reçus n'est pas présenté comme un environnement CI reproduit.
   Les sources/entrées de test sont vérifiées à nouveau, les tests déjà qualifiés
   restent locaux. L'état réel du VPS est toujours constaté de nouveau.

age assure la confidentialité et l'intégrité du chiffré, **pas l'identité de
l'expéditeur**. Celle-ci repose ici sur l'accès de publication du propriétaire,
le descripteur immuable dans la révision déployée et les octets vérifiés. Un cache
externe anonyme ou un reçu soumis par un tiers ne peut pas satisfaire cette chaîne.
Une compromission de l'atelier autorisé ou du compte GitHub propriétaire demeure
une limite de ce modèle ; aucune attestation indépendante n'est revendiquée.

La révision de construction et celle des opérateurs sont distinctes. Un correctif
de documentation ou d'exploitation ne reconstruit pas le même graphe Lisp ; le
préparateur compare ses sources avec l'empreinte qualifiée. Une modification de ce
graphe exige un nouvel artefact et les contrôles affectés. Les révisions exactes
et empreintes des ressources frontend restent également conservées.

Préparation et restauration peuvent se reprendre comme étapes du même déploiement,
sans validation humaine intermédiaire. L'activation exige une sauvegarde récente,
restaurée hors production, les ACL et le retour qualifiés. Le retour conserve les
bases actuelles et recopie les derniers SQLite/JSONL après arrêt du serveur commun.
Un opérateur indépendant est armé avant la bascule. Les sondes vérifient notamment
l'exécutable servi, les ressources publiques, le refus anonyme/MCP et une identité
falsifiée, les invariants et le redémarrage ; elles ne créent aucun contenu réel.

État au 11 octobre : protocole et opérateurs écrits, qualification locale en cours.
Envoi de l'asset refusé par uploads.github.com (401) ; release non publiée.
Transport Git chiffré préparé sans credential supplémentaire ni binaire dans main.
Aucun transfert ni activation effectués à ce stade. Les preuves
de restauration et d'accès réellement obtenues primeront sur cette description.

Soumission du candidat e522c2a : 108401335 octets chiffrés, trois parties de
40 Mio maximum dans le commit de transport29cde31. Le binaire296b7c89 et
sa construction158e4a5 sont inchangés. La médiation CI actuelle est liée au
commit Actions ; les opérateurs privés serveur restent ceux du bundlee522c2a.
Aucun code privé en clair ni binaire ajouté à main.
