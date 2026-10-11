# Audit de l’outillage MCP de développement

Sources officielles à commits complets, licences et 35 systèmes nécessaires
verrouillés dans mcp.lock.json ; distributions/patches du Nixpkgs déjà retenu,
empreintes NAR exactes. Aucun ajout au graphe ASDF métier ou runtime du produit.
L’audit de chargement et de routage précède l’installation/qualification ; il
ne démontre pas l’absence de vulnérabilité dans ces outils d’exécution de code.

cl-mcp 3.0.2 : système package-inferred, contribs SBCL posix/cltl2 et lecteur
Eclector, registres et verrous initialisés. Le pool vaut vrai par défaut ;
MCP_NO_WORKER_POOL non vide et :worker-pool nil le désactivent. Lancer HTTP
local dans l’image applicative avec les deux contrôles ; aucun init-hook de
worker. HTTP protège Origin/Host, sessions et jeton optionnel. Chargement seul
sans serveur ; outils de fichiers/eval puissants réservés aux sources autorisées.
Groupes optionnels cl-spec/clhs désactivés, aucun cl-harness.

Tron 0.1.0 : définitions/registres, whitelist et configuration par défaut au
chargement, pas de serveur automatique par ASDF. JSON utilise jzon ; quelques
formes compile/load appellent ql:quickload (jzon/usocket/threads). Le client
Quicklisp officiel verrouillé est donc nécessaire, avec répertoire privé et
dists vide précréé pour éviter une distribution initiale téléchargée implicitement.
Tous les systèmes viennent d’ASDF/Nix ; aucun update-client/update-dist, Roswell,
devenv, autre runtime ou téléchargement à chaud. La configuration de lancement
borne les fichiers de configuration et interdit les cibles non locales.

Le transport HTTP officiel Tron est localhost, sans authentification, avec
limites de taille/temps/débit. Il modifie le dispatch global Hunchentoot : utiliser
un processus d’outillage distinct sans charger l’application, connecté au Swank
du PID applicatif. Ses modes fallback locaux/managed-process ne prouvent pas le
raccordement : seules les commandes Swank/unified connectées servent au débogage.
Pas de lancement automatique d’une seconde application.

Swank 2.29.1 : version/patches Nixpkgs exacts (Lisp public domain ; client Emacs
GPL non chargé), système séparé sans écoute au chargement. Démarrage explicite
loopback, sans user init arbitraire. Variables et piles contiennent des valeurs :
fixtures synthétiques uniquement, sorties bornées, journaux sans secrets.

Transitives : BSD/MIT/public domain/zlib et Apache-2.0 (log4cl), selon les sources/ASD enregistrées,
aucun changement de licence de nos dépôts. Hunchentoot et CFFI peuvent charger
OpenSSL et définir des handlers/threads ; utiliser les DSO du même Nixpkgs et
un cache FASL de développement distinct, sans connexion HTTP sortante ou DB de
production. Local-time lit son référentiel de fuseaux ; log4cl initialise des
loggers ; MGL/autoload définit des hooks ASDF/readtables sans serveur. Swank garde
les caches/piles dans l’image, aucun état pédagogique durable modifié ici.

Qualification réelle réussie par `python3 scripts/qualifier-mcp.py` : installation,
serveurs locaux, connexion depuis cet agent hébergé via son outil d’exécution et
le pont HTTP, identité PID83928/marqueur, objet11→12 observé des deux côtés ;
condition réelle, pile de l’événement DEBUG, locaux40/2, correction source compilée,
restart résultat42 et effet préalable exécuté une seule fois. Pas d’enregistrement
natif dans le catalogue Codex ; le pont est effectivement utilisable ici.
Les preuves synthétiques machine restent dans state/outils-mcp, sans publication
autorisée par un reçu local. Les outils ne sont pas intégrés au produit livré.

Limites constatées : repl_backtrace/swank_backtrace inspectent le worker RPC
courant dans cette révision. La pile suspendue est celle de l’événement DEBUG,
ses variables sont interrogées avec repl_frame_locals. Le fallback ASDF de cl-mcp
ne compte pas les tests ; la qualification exige le marqueur émis après trois
assertions dans notre test-op. Aucun « succès » déduit de success:null.

Installation constatée : les sources ASDF MGL/autoload sont imbriquées, donc
registre :tree (pas seulement :directory). Copie Quicklisp privée rendue writable,
sources intactes, dists vide. La révision Tron amont échoue sur trois mots-clés
de breakpoints ; patch local Nix de trois schémas et trois appels, rien d’autre.
Son outil optionnel d’installation de skills contient aussi un appel de mauvaise
arité. Le raccordement charge le sous-système officiel cl-tron-mcp/core, qui
inclut le serveur/transport et tous les outils de développement nécessaires,
sans cette fonction facultative. Aucun outil d’installation de skills qualifié.
Ces erreurs ne sont ni ignorées par une politique ASDF permissive ni corrigées
dans un dépôt tiers. Le scénario de débogage reste intégralement exigé.
