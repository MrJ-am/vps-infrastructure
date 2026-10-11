# Outillage frontend verrouillé

Autorisation : amendement du 11 octobre 2026. Développement/test seulement,
aucun runtime Node dans le serveur métier. Nixpkgs c5c4a43 inchangé.

CLI officiel node-elm-review tag v2.13.5 : paquet Nix2.13.5, code package.json
annonçant encore2.13.4 ; les deux valeurs sont conservées, sans les confondre.
BSD-3-Clause, Node>=22 ; Node24.19.0 du Nixpkgs retenu. Source fetchFromGitHub et
npmDepsHash exacts dans outils.lock.json. 111 paquets npm effectivement présents
inventoriés avec versions, URL/intégrité du package-lock, licences et dépendances.
Le packaging Nix retire le prepare « elm-tooling install » ; aucune installation
opportuniste d'un compilateur, de framework ou de service. Compilateur et elm-test
déjà employés par Matheval conservés. Pas de fix/watch/template distant/suppressions.

Bibliothèque elm-review2.15.0 correspondant au template de cette révision CLI ;
elm-syntax7.3.8. Règle existante NoUnused.Dependencies de elm-review-unused1.2.3
compatible avec cette API, BSD-3-Clause. Sources et graphe lus avant sélection ;
pas de paquet de règles généraliste introduit pour forcer des refontes sans rapport.
Les archives nouvelles sont vérifiées contre endpoint.json officiel et verrouillées
par empreinte Nix ; les sources des19 paquets Elm (dont ceux déjà présents) ont
une liste d'empreintes des fichiers de code. Licences/dépendances/effets consignés.

Inventaire étendu de l'atelier logo : il utilise déjà elm-animator2.0.0. Le registre
officiel confirme cette version publiée et ses nouveaux modules Timeline/Value/
Transition, incompatible avec l'ancien Animator.Inline1.1.1 de Matheval. La cible
commune est donc2.0.0, avec migration explicite et requalification des parcours ;
aucune mise à jour à la dernière version supposée. Version1.1.1 conservée comme
référence historique. BSD-3-Clause ; Color1.0.0 et elm-bezier2.0.0 déjà présents
dans l'atelier, elm-units2.10.0 de Matheval ne sera retiré que sans consommateur.
Timeline/calculs purs au chargement ; les subscriptions utilisent Browser.Events
seulement lorsque le modèle progresse. Le socle commun doit
encore exploiter réellement ces fonctions avec elm-ui, respecter reduced-motion
et arrêter les frames inutiles : la présence du paquet n'en constitue pas la preuve.

Installation Nix CLI et compilation des règles réussies ; 21 tests Review.Test
passent. La commande canonique accepte une référence Html de type, refuse une
présentation H.div et refuse une dépendance inutilisée. Le rejet vérifie le nom
de règle et le type de rapport, pour distinguer violation et erreur d'installation.
Ces résultats ne qualifient pas les interfaces actuelles, effectivement refusées.

Limites : un AST Elm ne couvre pas HTML/CSS/JS externes ni l'expérience animée.
Le contrôle complémentaire et les tests navigateur restent nécessaires. Les
exceptions techniques portent sur fonctions/symboles précis, source commune
réelle et attributs ARIA littéraux ; aucune exclusion ou suppression générale.
