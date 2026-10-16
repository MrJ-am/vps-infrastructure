# Forgejo — état du 16 octobre 2026

Sources publiées et candidat construit sur le VPS, **sans activation**.
[Préparation réussie](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38880366362).
Source verrouillée : `228db509abb2f36ad154333247cd521a77b54bea`.

- URL prévue : `https://git.mrg.am/`. Le DNS public renvoie NXDOMAIN.
  Enregistrement requis : A `git.mrg.am` → `187.77.95.158`, sans AAAA non qualifié.
  Aucun accès de gestion de cette zone Netim n’est disponible dans cette session.
- Versions du candidat : Forgejo **16.0.3**, Pandoc **3.7.0.2**, MathJax et polices
  **4.1.3**, archives verrouillées par SHA-256. Les services ne sont pas activés.
- Nix : `module.nix`, `integration.nix`, `assets.nix`. Paramètres et actifs dans
  le même dossier ; opérateurs/testeurs `scripts/forgejo-*.py`, régression
  `tests/forgejo-integration.nix`, descripteur `operations/forgejo-candidat.json`.
  Le workflow administratif central est étendu, aucun nouveau workflow/runner.
- L’existant inspecté n’a pas de flake : entrée classique `/etc/nixos/configuration.nix`.
  Toute sa chaîne d’imports est conservée dans le candidat, sans migration générale.

## Tests réellement effectués

Qualification locale sur le vrai Forgejo, avec SQLite et HTTP en boucle locale :
README et trois Org en sous-répertoire, Pandoc confirmé par les spans produits,
composition MathJax CHTML effective dans Chromium, huit vues 1280/390 px.
Quatre délimiteurs mathématiques, align, fractions, matrice et référence numérotée ;
structure, liens et image, injections HTML/JS refusées, zéro erreur JS ou ressource
manquante, aucune ressource CDN. Expressions longues confinées au défilement du
conteneur, page mobile sans débordement. Authentification, refus anonyme,
inscriptions fermées, clone/push HTTP et SSH, puis mêmes contrôles après redémarrage
du service local avec conservation du commit Git. Cette instance n’est pas le VPS.

Nix : assertions et régression de priorité HBA/timer ACME réussies ; constructeur
Nginx/Gixy avec zéro problème. Sur le VPS, construction complète réussie, unités
protégées et hôtes conservés, anciens HBA et renouvellements TLS inchangés.
Sauvegarde age et restauration isolée de 38 tables Vision, 6 Matheval et 100
mrjam_identite avec empreintes identiques, sans interruption de production.
Les 25 sondes HTTP existantes passent avec TLS vérifié. Génération active conservée.
Détails : `qualification-locale.json`, `preparation-vps.json`.

## Accès et contrôles restant à faire

L’activation est bloquée avant toute bascule tant que le DNS requis n’existe pas.
Restent à vérifier sur la production : service Forgejo/PostgreSQL, certificat
ACME/HTTPS, Git externe HTTPS/SSH, dépôt privé de test et rendu navigateur, sauvegarde
Forgejo/restauration isolée, retour indépendant et persistance après redémarrage.
Aucun redémarrage complet du VPS n’a été effectué.

Aucun compte Forgejo de production n’a été créé. Après activation, le bootstrap
créera `mrjam-admin` et enregistrera son résultat dans
`/var/lib/forgejo-bootstrap/initial-admin.txt`, root uniquement, sans mot de passe
dans les arguments, le store ou les journaux. Accès par le canal administratif
existant/hPanel ; changement de mot de passe imposé à la première connexion.
La procédure détaillée et les sauvegardes déclarées sont dans `README.md`.
