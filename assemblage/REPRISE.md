# Reprise — mission du 11 octobre 2026

Production : ancienne architecture toujours active. Étape 1 non terminée ;
Kanidm n’est pas commencé. Aucun apprentissage, compte ou participation réelle
n’a été créé, fermé ou effacé pendant les qualifications.

1. Inventaire réel, sources, cadre et graphe ASDF : réalisés.
2. Portage Matheval et auxiliaires Vision, interfaces et orchestration centrale :
   réalisés et qualifiés localement ; qualification Nix/IdP réelle restante.
3. Candidat Nix exact, restauration/ACL/retour, bascule et contrôles de production :
   à achever. Le jalon exige invariants, accès/MCP et persistance au redémarrage.
4. Après ce constat uniquement : Kanidm réel, nouvelle identité liée explicitement
   au propriétaire métier ; retrait Keycloak après accès et récupération sûrs.

Le [manifeste](manifest.json) porte les six branches effectives et révisions
complètes publiées : Vision fcb35f8, Matheval/master d64f235, Logique 586ae18,
Style 1132afe, Signature c4a2067. La révision assembleur est le commit qui contient
le manifeste ; les reçus portent aussi les empreintes pertinentes.

Bibliothèques : Vision cœur/HTTP/administration/cycle/admission/fermeture,
Matheval calculs/collecte/statistiques/administration ; adaptateurs natifs libpq,
OpenSSL et SQLite, courriel durable/SMTP, client Keycloak provisoire. Le serveur
commun possède transport Unix, routage, connexions et tâches. Logique statique.
Aucune bibliothèque ne démarre de daemon ni ne migre une base au chargement.

Qualifications locales : 116 cas Matheval purs, 8000 tirages, 8003 cas natifs
JSON/OpenSSL, 40 parcours différentiels PostgreSQL/HTTP et concurrence ; 644 cas
administration et 141 admission, SQLite/MIME/SMTP STARTTLS, cycle et fermeture.
Même binaire : API/MCP Vision avec 40 parcours Alice/Bob concurrents et refus
croisés. 30/6 tables classées avec RLS/ACL et rôles effectifs vérifiés. Identité
synthétique : ces succès ne qualifient pas la chaîne Nginx/OIDC de production.

Dernier binaire local 22655808 : SBCL 2.5.2/ASDF 3.3.1, 40 FASL sans cache,
3,559 s de construction et 8,3669 s pour le différentiel/HTTP/redémarrage.
Les quatre documents Vision lus au chargement sont déclarés au graphe ASDF
et aux empreintes ; modification/rechargement dans une même image testés.
La CI prépare maintenant le Nixpkgs exact c5c4a43 et SBCL 2.6.4 du VPS, sans
mise à jour générale. Ce build Nix commun n’est pas encore exécuté/qualifié.

Frontends : commandes centrales construire/qualifier, worktrees temporaires,
quatre candidats privés et métadonnées adjacentes. Les trois versions de style
historiques restent verrouillées. Les derniers changements de pins ne changent
que quatre manifestes/reçus de révision ; ressources fonctionnelles identiques.
Vision historique/navigateur, Matheval données/construction et 56 parcours
navigateur réels sur le serveur commun, Logique correcteur/interface, atelier
Style complet et ressources/copie Signature passent. Un premier échec de clic
Firefox reste consigné, non reproduit sur vingt essais ciblés et deux campagnes
complètes ; cause inconnue. Les diagnostics restent privés. La dernière campagne
56/56 porte 5dd18de2 ; les corrections suivantes de quotas HTTP portent 22655808
et ont leur contrôle transport ciblé, sans prétendre réutiliser son reçu navigateur.

Recherche réelle : même modèle multilingual-MiniLM-L12-v2, révision e8f8c211,
onze fichiers verrouillés, profil CPU existant de 35 roues SHA256. Six paraphrases
rang 1, rappel 1 ; archives/modifications/alias/isolation vérifiés. Aucun changement
de stratégie de recherche. Les fixtures synthétiques restent hors production.
Reçus locaux non attestés : jamais une autorisation de publication CI.

CI satellite : treize recettes archivées exactement dans leurs composants,
aucun YAML actif/relais sur les cinq branches intégrées. GitHub a confirmé la
désactivation des workflows personnalisés, y compris ceux des anciennes branches.
Son workflow intégré Pages Matheval refuse PUT disable (422) ; build_type workflow,
dernière publication du 12 septembre, aucun déclencheur personnalisé conservé.
Ne pas annoncer sa désactivation distante. Le contenu existant est conservé.
L’ancien signal operations/vision et son coordinateur workflow_run sont archivés ;
plus d’attente de message, acquittement ou confirmation technique intermédiaire.

Référence VPS : run 38098717899, fichier reference-production.json. Génération
r6s7ags3 inchangée, SBCL 2.6.4/PG17.11/Keycloak26.7.3. Un compte Vision actif,
propriétaire cohérent, aucune relation étrangère/orpheline ; trois participations
Matheval ouvertes, conservées. RSS et latences mesurés séparément des plafonds.
CI infrastructure 38112469913 sur 2cd93ce : réussie, Python et Nix du module
sur paquet factice, syntaxe du build Nix vérifiée ;
les suites d’identité inchangées sont réutilisées depuis 38107422877, non rejouées.

Sauvegarde/restauration réelle : 38105867103 sur eff80b8, copie chiffrée des trois
bases et états durables, restauration cluster Unix privé, empreintes 30/6/100 tables
identiques. Clé éphémère enveloppée pour le destinataire existant puis détruite,
sans utiliser sa clé personnelle. Aucun arrêt ni écriture SQL de production.
[sauvegarde-transition.json](sauvegarde-transition.json) distingue données, ACL/rôles
et retour applicatif : les deux derniers restent à qualifier. Une nouvelle bascule
exige données et registre récents ; le retour du code ne restaure jamais une base
ancienne sur des écritures récentes. Conserver générations/archives et services tiers.

Blocage effectif : COMPONENTS_READ_TOKEN manque aux Actions de l’infrastructure
(run 38112469897 sur 2cd93ce, arrêt avant checkout privé). Le credential de session lit/pousse
les sources ; l’API secrets répond 403. Secret de lecture contenu limité à Vision
et Signature demandé au propriétaire ; ne jamais fournir sa valeur en conversation.
APIs protections/environments/deploy keys non accessibles : ne pas prétendre leur
nettoyage distant terminé. Ces permissions ne bloquent pas les travaux locaux.
Restent aussi l’installation des rôles/migration 026, transfert arrêté des états
SQLite/JSONL, qualification Nix/identité/MCP réels, ACL/restauration/retour ciblé,
bascule, invariants, probes et redémarrage de l’artefact réellement servi.
