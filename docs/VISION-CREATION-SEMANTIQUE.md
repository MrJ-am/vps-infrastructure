# Vision 2.5 — création sémantique publiée le 4 octobre 2026

Le propriétaire a demandé explicitement le déploiement. L'application et son
interface servent la révision `c0bfcac66b9ee52e282bb895ec6aed3921a86266`.
Le candidat VPS est `32a4c3d2ad0e39568fe16d7acdb2472a7f095fc2` (PR 26),
avec les modules pgvector/fournisseur revus dans la PR 25. PostgreSQL reste
17.11, avec ses données dans `/var/lib/postgresql/17`, sans écoute TCP.

## État réellement constaté

- Génération active et de démarrage :
  `/nix/store/y1azkcagkf54nq5vjn4j16g5v1c61c4c-nixos-system-nixos-26.05.8639.c5c4a43b0e80`.
- Nixpkgs conservé :
  `/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos`.
- Entrée NixOS : import de
  `/root/vision-semantique/32a4c3d2ad0e39568fe16d7acdb2472a7f095fc2/source/hosts/hostinger/vision-semantique.nix`.
  Conserver ce répertoire de sources, les deux releases applicatives, les
  rapports et les racines de GC `vision-semantique/<candidat>/{avant,apres}`.
- Ancienne génération protégée : `mabshi6mmisnabl5qb5hwldnkxiz2s25` ; anciennes
  releases Vision serveur/interface `3cbd57ff8d05798e3766fd0d6c93087739d8b608` conservées.
- Migration 016 installée, contrats SQL création/révision `1` et `6` ;
  **58 items, 58 embeddings**, dix-sept tables historiques préservées.
- Fournisseur `vision-embeddings.service` actif, local seulement, budget maximal
  2 Gio. MiniLM multilingue 384 dimensions, snapshot
  `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, onze fichiers SHA-256 verrouillés.
- Génération enregistrée après les contrôles ; retour automatique désarmé.
  Aucun redémarrage complet du VPS ni restauration de production effectué.

## Preuves et contrôles

- Audit actuel [37182284525](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37182284525) :
  services, ressources, PostgreSQL et 25 sondes HTTP/TLS conformes.
- CI du candidat [37200246228](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37200246228) :
  registres, syntaxe, configurations NixOS et restaurations en conteneur réussis.
- Construction réelle et restauration isolée
  [37200466652](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37200466652) :
  modèle/fournisseur construits avec le Nixpkgs installé, sauvegarde Vision
  restaurée dans un cluster indépendant sans TCP. Migration, backfill de 58 items,
  vrai serveur Lisp et vrais embeddings testés. Les six paraphrases sont au
  premier rang ; preuves, archives, alias et modifications vérifiés.
- Activation [37200705574](https://github.com/MrJ-am/vps-infrastructure/actions/runs/37200705574) :
  nouvelle sauvegarde après arrêt des écritures Vision, seconde restauration et
  mêmes essais, timer de retour autonome, génération temporaire, migration et
  vectorisation, puis liens serveur/interface. Empreintes des dix-sept tables
  historiques identiques avant/après migration et backfill.
- HTTPS : version 2.5, quinze outils MCP et préparation de création vérifiés ;
  « La capitale française est Paris » retrouve l'item historique correspondant.
  Aucun nouvel item ni séance de test créé en production. La préparation ajoute
  seulement une preuve technique. Les essais de création complets restent isolés.
- Artefact statique exact, rendu, police, login/logout, cookie, CSRF, origine,
  refus anonyme et Basic vérifiés. La connexion MCP existante depuis Work
  fonctionne après activation ; découverte OAuth et invariants d'authentification
  conservés. Nouvelle connexion SSH et 25 sondes HTTP/TLS réussies.

## Reprise et limites

Le point d'entrée actif inclut explicitement `vision-semantique.nix`. Un futur
changement système doit préserver pgvector et le fournisseur : ne pas reconstruire
aveuglément le seul `logique.nix`, qui ne les active pas par défaut. Conserver
le Nixpkgs installé et auditer à nouveau les sources/générations avant bascule.

Le retour d'essai conserve les nouvelles données et fonctions SQL ; l'ancien
client ne peut plus créer par sa preuve lexicale. Après enregistrement, ce retour
est volontairement inopérant : un retour ultérieur est une opération distincte,
sans restauration automatique de base. Les sauvegardes et journaux privés restent
dans `/root/vision-semantique/<candidat>/`, jamais copiés en clair dans Git.

Le corpus réduit mesure un rappel de 100 %, pas un rappel universel. Dix candidats
comprennent neuf autres propositions en moyenne ; le LLM reste le filtre final.
Recherche exacte adaptée au volume actuel, sans HNSW. Le démarrage après un reboot
réel n'a pas été testé. Les clients MCP ayant conservé l'ancien catalogue doivent
actualiser leur connexion pour charger `preparer_creation_item` et ses instructions.
Architecture applicative : `MrJ-am/vision`, `docs/CREATION-ITEMS.md`.
